import base64
import hashlib
import uuid
from datetime import timedelta

import bcrypt  # pip install bcrypt
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models import F
from django.utils import timezone
from django.conf import settings

BCRYPT_ROUNDS = 12
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = timedelta(minutes=15)


def _prehash(raw_password: str) -> bytes:
    """
    bcrypt only reads the first 72 bytes and chokes on NUL bytes.
    SHA-256 + base64 gives a fixed 44-byte, NUL-free input, so long
    passwords/passphrases are fully used (same idea as Django's BCryptSHA256).
    """
    digest = hashlib.sha256(raw_password.encode("utf-8")).digest()
    return base64.b64encode(digest)


# Used to burn the same CPU time when the user doesn't exist (anti-timing attack)
_DUMMY_HASH = bcrypt.hashpw(_prehash("dummy-password"), bcrypt.gensalt(BCRYPT_ROUNDS))

class SocialAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    provider = models.CharField(max_length=20)   # "google", "apple"
    uid = models.CharField(max_length=255)       # Google's "sub"

    class Meta:
        unique_together = ("provider", "uid")


class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra):
        if not username or not email:
            raise ValueError("username and email are required")
        user = self.model(
            username=username.strip(),
            email=self.normalize_email(email).lower(),
            **extra,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(username, email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    # Random UUID primary key: ids can't be guessed or enumerated (/users/1, /users/2 ...)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(max_length=254, unique=True)

    # `password` (bcrypt hash, never plaintext) and `last_login` come from AbstractBaseUser

    is_active = models.BooleanField(default=True)   # soft-disable instead of deleting
    is_staff = models.BooleanField(default=False)   # Django admin access
    email_verified = models.BooleanField(default=False)

    # --- Brute-force protection ---
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    # --- Session / token control ---
    # Embed this number in every JWT. Bump it to invalidate all existing
    # tokens for the user (password change, "log out everywhere", compromise).
    token_version = models.PositiveIntegerField(default=0)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    class Meta:
        indexes = [models.Index(fields=["email"])]

    def __str__(self):
        return self.username

    def get_full_name(self):
        return self.username

    def get_short_name(self):
        return self.username

    # ---------- Password handling (bcrypt) ----------
    def set_password(self, raw_password):
        hashed = bcrypt.hashpw(_prehash(raw_password), bcrypt.gensalt(BCRYPT_ROUNDS))
        self.password = hashed.decode("utf-8")
        self.password_changed_at = timezone.now()
        self.token_version = (self.token_version or 0) + 1  # revoke old tokens

    def check_password(self, raw_password):
        try:
            return bcrypt.checkpw(_prehash(raw_password), self.password.encode("utf-8"))
        except (ValueError, AttributeError):
            return False

    @staticmethod
    def dummy_check(raw_password):
        """Call when the user wasn't found so response time looks the same."""
        bcrypt.checkpw(_prehash(raw_password), _DUMMY_HASH)

    # ---------- Lockout ----------
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self):
        # F() makes the increment atomic, so parallel guesses can't slip past the counter
        type(self).objects.filter(pk=self.pk).update(
            failed_login_attempts=F("failed_login_attempts") + 1
        )
        self.refresh_from_db(fields=["failed_login_attempts"])
        if self.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            self.locked_until = timezone.now() + LOCKOUT_DURATION
            self.save(update_fields=["locked_until"])

    def register_successful_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = timezone.now()
        self.save(update_fields=["failed_login_attempts", "locked_until", "last_login"])