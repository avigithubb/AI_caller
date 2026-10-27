from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.conf import settings

from vonage import Auth, Vonage
from vonage_voice import CreateCallRequest, Phone, Talk, ToPhone
import logging

from .models import CallRequest
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

import os
import json
import re
import jwt

VONAGE_APPLICATION_ID = getattr(settings, "VONAGE_APPLICATION_ID", os.getenv("VONAGE_APPLICATION_ID", ""))
VONAGE_PRIVATE_KEY = getattr(
    settings,
    "VONAGE_PRIVATE_KEY",
    os.getenv("VONAGE_PRIVATE_KEY_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "private.key")),
)
VONAGE_VIRTUAL_NUMBER = getattr(settings, "VONAGE_VIRTUAL_NUMBER", os.getenv("VONAGE_VIRTUAL_NUMBER", ""))
VOICE_TO_NUMBER = getattr(settings, "VOICE_TO_NUMBER", os.getenv("VOICE_TO_NUMBER", ""))
MAX_ATTEMPTS = 5 
NUMBER_RE = re.compile(r"^\d{7,15}$")
MAX_TEXT_LENGTH = 1000

# logger = logging.getLogger(__name__)

# client = Vonage(Auth(
#     application_id=VONAGE_APPLICATION_ID,
#     private_key=VONAGE_PRIVATE_KEY,
# ))

def home(request):
    return JsonResponse({
        "message": "Django API is working"
    })

# def _serialize(call):
#     return {
#         "id": call.id,
#         "to_number": call.to_number,
#         "generated_text": call.generated_text,
#         "max_attempts": call.max_attempts,
#         "attempts_used": call.attempts_used,
#         "attempts_remaining": call.max_attempts - call.attempts_used,
#         "created_at": call.created_at,
#     }

# def _error(message, status=400):
#     return JsonResponse(
#         {
#             "success": False,
#             "error": message,
#         },
#         status=status,
#     )

# import json
# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# from django.views.decorators.http import require_POST


# @csrf_exempt
# @require_POST
# def make_call(request):
#     try:
#         data = json.loads(request.body or "{}")
#     except json.JSONDecodeError:
#         return JsonResponse({"success": False, "error": "Invalid JSON body."}, status=400)

#     number_to_call = f"91{str(data.get("phone") or "").strip()}"
#     print(number_to_call)
#     message = str(data.get("prompt") or "").strip()

#     if not number_to_call or not message:
#         return JsonResponse(
#             {"success": False, "error": "'phone' and 'prompt' are required."}, status=400
#         )
    
#     try:
#         response = client.voice.create_call(
#             CreateCallRequest(
#                 ncco=[Talk(text=message, language="en-IN")],
#                 to=[ToPhone(number=number_to_call.lstrip("+"))],
#                 from_=Phone(number=VONAGE_VIRTUAL_NUMBER),
#                 event_url=[
#                     "https://licorice-knee-confidant.ngrok-free.dev/api/calls/vonage/event/"
#                 ],
#                 event_method="POST",
#             )
#         )
#     except Exception as exc:
#         logger.exception("Vonage call failed")
#         return JsonResponse({"success": False, "error": str(exc)}, status=502)

#     return JsonResponse({
#         "success": True,
#         "uuid": response.uuid,
#         "status": response.status,
#     })

# @csrf_exempt
# def vonage_event(request):

#     try:
#         data = json.loads(request.body or "{}")
#     except json.JSONDecodeError:
#         return HttpResponse(status=400)

#     # status = data.get("status")
#     # uuid = data.get("uuid")

#     # if status == "answered":
#     #     print("✅ Person answered")

#     # elif status == "unanswered":
#     #     print("❌ Person did not answer")

#     # elif status == "ringing":
#     #     print("📞 Phone is ringing")

#     # elif status == "completed":
#     #     print("☎️ Call completed")

#     logger.info(
#         "Vonage event: uuid=%s status=%s reason=%s",
#         data.get("uuid"), data.get("status"), data.get("reason"),
#     )

#     return JsonResponse({"received": True})

# # TODO: create a route to fetch the user requested data from the dashboard. Like the number to, attempt remaining out of 5 
# #, generated text etc. and we are going to store that data to our db. 

# @csrf_exempt  # token-in-header API, no cookies
# @require_http_methods(["GET", "POST"])
# # @permission_classes([IsAuthenticated])
# def call_requests(request):
#     # GET -> everything the logged-in user has submitted, with attempts remaining
#     if request.method == "GET":
#         items = CallRequest.objects.filter(user=request.user)[:100]
#         return JsonResponse({"success": True, "results": [_serialize(c) for c in items]})
 
#     # POST -> store a new request from the dashboard
#     try:
#         data = json.loads(request.body)
#         if not isinstance(data, dict):
#             raise ValueError
#     except (ValueError, UnicodeDecodeError):  # JSONDecodeError is a ValueError
#         return _error("Invalid JSON.", 400)
 
#     # --- to_number ---
#     to_number = re.sub(r"[\s\-+]", "", str(data.get("to_number") or ""))
#     if not NUMBER_RE.match(to_number):
#         return _error("to_number must be 7-15 digits including country code.", 400)
 
#     # --- generated_text ---
#     generated_text = str(data.get("generated_text") or "").strip()
#     if not generated_text:
#         return _error("generated_text is required.", 400)
#     if len(generated_text) > MAX_TEXT_LENGTH:
#         return _error(f"generated_text must be at most {MAX_TEXT_LENGTH} characters.", 400)
 
#     # --- attempts_remaining (out of 5); defaults to a full 5 if not sent ---
#     raw_remaining = data.get("attempts_remaining", MAX_ATTEMPTS)
#     if isinstance(raw_remaining, bool) or not isinstance(raw_remaining, int) \
#             or not 0 <= raw_remaining <= MAX_ATTEMPTS:
#         return _error(f"attempts_remaining must be an integer from 0 to {MAX_ATTEMPTS}.", 400)
 
#     # --- store with the ORM ---
#     call = CallRequest.objects.create(
#         user=request.user,
#         to_number=to_number,
#         generated_text=generated_text,
#         max_attempts=MAX_ATTEMPTS,
#         attempts_used=MAX_ATTEMPTS - raw_remaining,
#     )
#     return JsonResponse({"success": True, "result": _serialize(call)}, status=201)

logger = logging.getLogger(__name__)

S = CallRequest.Status

# Vonage call status -> our CallRequest.Status
VONAGE_STATUS_MAP = {
    "started": S.PENDING,
    "ringing": S.RINGING,
    "answered": S.ANSWERED,
    "machine": S.ANSWERED,
    "completed": S.COMPLETED,
    "unanswered": S.UNANSWERED,
    "timeout": S.UNANSWERED,
    "busy": S.FAILED,
    "rejected": S.FAILED,
    "cancelled": S.FAILED,
    "failed": S.FAILED,
}

# Webhooks can arrive out of order, so a status may only move forward.
STATUS_RANK = {
    S.PENDING: 0,
    S.RINGING: 1,
    S.ANSWERED: 2,
    S.COMPLETED: 3,
    S.UNANSWERED: 3,
    S.FAILED: 3,
}
FINAL_STATUSES = {S.COMPLETED, S.UNANSWERED, S.FAILED}

# Initialize Vonage client safely
client = None

# 1. Check for raw private key content in env (e.g. from Render)
# 2. Otherwise fall back to local file path
private_key_content = os.getenv("VONAGE_PRIVATE_KEY")
if not private_key_content and os.path.exists(VONAGE_PRIVATE_KEY):
    try:
        with open(VONAGE_PRIVATE_KEY, "r") as f:
            private_key_content = f.read()
    except Exception as e:
        logger.warning(f"Could not read Vonage key file: {e}")

if VONAGE_APPLICATION_ID and private_key_content:
    try:
        # Replace literal '\n' characters if passed as a single-line string in env
        formatted_key = private_key_content.replace("\\n", "\n").strip()
        client = Vonage(Auth(
            application_id=VONAGE_APPLICATION_ID,
            private_key=formatted_key,
        ))
    except Exception as exc:
        logger.error(f"Failed to initialize Vonage client: {exc}")
else:
    logger.warning("Vonage credentials not found; Vonage calling is disabled.")
# --------------------------------------------------------------------------
# Helpers (replace your existing _serialize and _error with these)
# --------------------------------------------------------------------------
def _serialize(call):
    return {
        "id": call.id,
        "to_number": call.to_number,
        "generated_text": call.generated_text,
        "status": call.status,
        "max_attempts": call.max_attempts,
        "attempts_used": call.attempts_used,
        "attempts_remaining": call.attempts_remaining,
        "created_at": call.created_at,
        "updated_at": call.updated_at,
    }


def _error(message, status=400):
    return JsonResponse({"success": False, "error": message}, status=status)


def get_user_from_request(request):
    """Plain-Django version of authenticate_request.
    Returns (user, None) or (None, error JsonResponse)."""
    parts = request.headers.get("Authorization", "").split(" ")
    if len(parts) != 2 or parts[0] != "Bearer" or not parts[1]:
        return None, _error("Authorization token is required.", 401)

    try:
        payload = jwt.decode(parts[1], settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, _error("Token has already expired.", 401)
    except jwt.InvalidTokenError:
        return None, _error("Invalid JWT token.", 401)

    User = get_user_model()
    try:
        user = User.objects.get(pk=payload.get("sub"))
    except (User.DoesNotExist, ValueError, ValidationError):
        return None, _error("User not found.", 401)

    # If your logout works by bumping a token version (the "ver" claim),
    # compare payload["ver"] with that field on the user here as well.
    return user, None


# --------------------------------------------------------------------------
# POST /api/calls/make-call/
# --------------------------------------------------------------------------
@csrf_exempt
@require_POST
def make_call(request):
    user, err = get_user_from_request(request)
    if err:
        return err

    try:
        data = json.loads(request.body or "{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return _error("Invalid JSON body.")

    if not client:
        return _error("Calling service is not configured on this server.", 503)

    phone = "".join(ch for ch in str(data.get("phone") or "") if ch.isdigit())
    message = str(data.get("prompt") or "").strip()

    # Check the raw values first (the old check ran after adding "91",
    # so it could never fail for a missing phone number).
    if not phone or not message:
        return _error("'phone' and 'prompt' are required.")

    # 10 digits = local Indian number, add the country code.
    # Anything longer is assumed to already include it.
    number_to_call = f"91{phone}" if len(phone) == 10 else phone

    # Save first, so we have an id to put in the event URL (no race with webhooks).
    call = CallRequest.objects.create(
        user=user,
        to_number=number_to_call,
        generated_text=message,
    )

    base_url = getattr(settings, "PUBLIC_BASE_URL", "https://ai-caller-k6r2.onrender.com")
    event_url = f"{base_url}/api/calls/vonage/event/?cr={call.id}"

    try:
        response = client.voice.create_call(
            CreateCallRequest(
                ncco=[Talk(text=message, language="en-IN")],
                to=[ToPhone(number=number_to_call)],
                from_=Phone(number=VONAGE_VIRTUAL_NUMBER),
                event_url=[event_url],
                event_method="POST",
            )
        )
    except Exception:
        logger.exception("Vonage call failed")
        call.status = S.FAILED
        call.save(update_fields=["status", "updated_at"])
        return _error("Couldn't place the call. Please try again.", 502)

    call.vonage_uuid = response.uuid
    call.save(update_fields=["vonage_uuid", "updated_at"])

    return JsonResponse({
        "success": True,
        "id": str(call.id),       # the app polls with this
        "uuid": response.uuid,
        "status": call.status,
    })


# --------------------------------------------------------------------------
# POST /api/calls/vonage/event/   (called by Vonage, no JWT)
# --------------------------------------------------------------------------
@csrf_exempt
@require_POST
def vonage_event(request):
    try:
        data = json.loads(request.body or "{}")
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        return JsonResponse({"received": False}, status=400)

    vonage_uuid = data.get("uuid")
    vonage_status = data.get("status")
    logger.info(
        "Vonage event: uuid=%s status=%s reason=%s",
        vonage_uuid, vonage_status, data.get("reason"),
    )

    new_status = VONAGE_STATUS_MAP.get(vonage_status)
    if new_status is None:
        return JsonResponse({"received": True})

    # Find the row: by the id we put in the URL, falling back to the Vonage uuid.
    call = None
    cr = request.GET.get("cr")
    if cr:
        try:
            call = CallRequest.objects.filter(pk=cr).first()
        except (ValueError, ValidationError):
            call = None
    if call is None and vonage_uuid:
        call = CallRequest.objects.filter(vonage_uuid=vonage_uuid).first()
    if call is None:
        return JsonResponse({"received": True})

    # Ignore late or out-of-order events
    if call.status in FINAL_STATUSES or STATUS_RANK[new_status] < STATUS_RANK[call.status]:
        return JsonResponse({"received": True})

    if call.status != new_status:
        call.status = new_status
        fields = ["status", "updated_at"]
        if vonage_uuid and not call.vonage_uuid:
            call.vonage_uuid = vonage_uuid
            fields.append("vonage_uuid")
        call.save(update_fields=fields)

    return JsonResponse({"received": True})


# --------------------------------------------------------------------------
# GET /api/calls/status/<uuid>/   (called by the app)
# --------------------------------------------------------------------------
@require_GET
def call_status(request, call_id):
    user, err = get_user_from_request(request)
    if err:
        return err

    call = CallRequest.objects.filter(pk=call_id, user=user).first()
    if call is None:
        return _error("Call not found.", 404)

    return JsonResponse({"success": True, "result": _serialize(call)})
