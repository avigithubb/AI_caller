from django.db import models
from django.conf import settings
import hashlib
import uuid
# Create your models here.

class CallRequest(models.Model):
    """One dashboard-submitted call request, owned by a user."""

    class Status(models.TextChoices):
        PENDING = "pending"
        RINGING = "ringing"
        ANSWERED = "answered"
        UNANSWERED = "unanswered"
        COMPLETED = "completed"
        FAILED = "failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="call_requests")
    user = models.ForeignKey(
            settings.AUTH_USER_MODEL,
            on_delete=models.CASCADE,
            related_name="call_requests",
        )

    to_number = models.CharField(max_length=15)  # digits only, e.g. 919876543210
    generated_text = models.TextField(blank=True, default="")  # text the call will speak
    attempts_used = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    vonage_uuid = models.CharField(max_length=64, blank=True, db_index=True)  # for webhook lookups

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    attempts_used__lte=models.F("max_attempts")
                ),
                name="attempts_used_lte_max_attempts",
            )
        ]

    @property
    def attempts_remaining(self):
        return max(0, self.max_attempts - self.attempts_used)

    def __str__(self):
        return f"{self.to_number} ({self.attempts_used}/{self.max_attempts})"