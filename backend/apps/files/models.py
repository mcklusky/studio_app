import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.organizations.models import Organization


class Attachment(models.Model):
    """Private file metadata; physical storage remains behind a private adapter."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="attachments")
    storage_key = models.CharField(max_length=500, unique=True)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    file_size = models.PositiveBigIntegerField(validators=[MinValueValidator(1)])
    purpose = models.CharField(max_length=80)
    owner_type = models.CharField(max_length=80)
    owner_id = models.UUIDField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_attachments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["organization", "owner_type", "owner_id"], name="attachment_owner_idx")]
