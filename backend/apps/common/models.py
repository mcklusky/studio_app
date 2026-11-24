import uuid

from django.conf import settings
from django.db import models


class IdempotencyRecord(models.Model):
    """Stored result of a retry-safe write, keyed by the client's Idempotency-Key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="idempotency_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="idempotency_records")
    scope = models.CharField(max_length=80)
    key = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "scope", "key"], name="uniq_idempotency_key")]


class DocumentSequence(models.Model):
    """Per-organization counter for human-readable numbers (PO-0001, INV-0001...)."""

    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE, related_name="document_sequences")
    key = models.CharField(max_length=20)
    next_value = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="uniq_document_sequence")]
