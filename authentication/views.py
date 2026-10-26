import logging

logger = logging.getLogger(__name__)
import json
from datetime import datetime, timedelta, timezone

import jwt  # pip install PyJWT
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from google.oauth2 import id_token
from google.auth.transport import requests as g_requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from .models import SocialAccount

User = get_user_model()

JWT_ALGORITHM = "HS256"
JWT_LIFETIME = timedelta(minutes=15)


def _json_body(request):
    try:
        data = json.loads(request.body)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _error(message, status):
    return JsonResponse({"success": False, "message": message}, status=status)


@csrf_exempt
@require_POST
def register(request):
    data = _json_body(request)
    if data is None:
        return _error("Invalid JSON.", 400)

    username = str(data.get("username") or "").strip()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")

    if not username or not email or not password:
        return _error("Username, email and password are required.", 400)

    # Enforce the AUTH_PASSWORD_VALIDATORS from settings.py (length, common, numeric...)
    try:
        validate_password(password)
    except ValidationError as e:
        return JsonResponse({"success": False, "message": list(e.messages)}, status=400)

    try:
        User.objects.create_user(username=username, email=email, password=password)
    except IntegrityError:  # unique constraint (also covers race conditions)
        return _error("User already exists.", 409)

    return JsonResponse({"success": True, "message": "User created."}, status=201)


@csrf_exempt
@require_POST
def login(request):
    data = _json_body(request)
    if data is None:
        return _error("Invalid JSON.", 400)

    identifier = str(data.get("username") or data.get("email") or "").strip()
    password = str(data.get("password") or "")

    if not identifier or not password:
        return _error("Username/email and password are required.", 400)

    user = User.objects.filter(
        Q(username=identifier) | Q(email=identifier.lower())
    ).first()

    generic_failure = _error("Invalid credentials.", 401)

    # Unknown user: still burn a bcrypt comparison so timing doesn't leak existence
    if user is None:
        User.dummy_check(password)
        return generic_failure

    if not user.is_active or user.is_locked():
        User.dummy_check(password)
        return generic_failure

    if not user.check_password(password):
        user.register_failed_login()
        return generic_failure

    user.register_successful_login()

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "ver": user.token_version,  # compare against DB when verifying to allow revocation
        "iat": now,
        "exp": now + JWT_LIFETIME,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)

    return JsonResponse({"success": True, "token": token}, status=200)

import jwt
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status


@api_view(["POST"])
def logout(request):

    # 1. Check whether Authorization header exists
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        return Response(
            {"error": "Authorization token is required."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # 2. Validate Bearer format
    parts = auth_header.split(" ")

    if len(parts) != 2 or parts[0] != "Bearer":
        return Response(
            {"error": "Invalid authorization header format."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    token = parts[1]

    # 3. Make sure token isn't empty
    if not token:
        return Response(
            {"error": "JWT token is missing."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # 4. Decode and validate JWT
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"]
        )

    except jwt.ExpiredSignatureError:
        return Response(
            {"error": "Token has already expired."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    except jwt.InvalidTokenError:
        return Response(
            {"error": "Invalid JWT token."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # 5. Successful logout
    return Response(
        {
            "success": True,
            "message": "Logged out successfully."
        },
        status=status.HTTP_200_OK
    )

class GoogleAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = (
            request.data.get("id_token")
            or request.data.get("credential")
            or request.data.get("token")
        )
        if not token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header.split(" ", 1)[1].strip()

        if not token:
            return Response(
                {"detail": "id_token or credential is required"},
                status=400,
            )

        try:
            info = id_token.verify_oauth2_token(
                token, g_requests.Request(), settings.GOOGLE_WEB_CLIENT_ID
            )
        except ValueError as e:
            logger.error("Google token verification failed: %s", e)
            return Response(
                {"detail": f"Invalid Google token: {str(e)}"},
                status=400,
            )

        sub = info["sub"]
        email = info.get("email")
        verified = info.get("email_verified", False)

        # 1. Returning Google user
        account = SocialAccount.objects.filter(provider="google", uid=sub).first()
        if account:
            user = account.user
        else:
            # 2. Existing email user: link (only if Google verified the email)
            user = User.objects.filter(email__iexact=email).first() if (email and verified) else None
            # 3. New user: this is the signup
            if not user:
                username = email or f"google_{sub}"
                if User.objects.filter(username=username).exists():
                    username = f"google_{sub}"
                user = User.objects.create_user(
                    username=username,
                    email=email or "",
                    password=None,
                    email_verified=verified,
                )
            SocialAccount.objects.create(user=user, provider="google", uid=sub)

        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.get_full_name(),
                "username": user.username,
            },
        })
    