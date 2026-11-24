from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from django.db import models

from apps.audit.models import AuditEvent
from apps.common.middleware import get_request_id

# Fields never copied into an audit summary, whatever the model.
SENSITIVE_FIELDS = {"password", "phone", "email", "address", "notes", "token", "secret"}


def _safe_value(value):
    if isinstance(value, models.Model):
        return str(value.pk)
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def changed_fields(instance, data):
    """Summarise which fields a write touched, without copying sensitive values."""
    summary = {}
    for name, value in data.items():
        if name in SENSITIVE_FIELDS:
            summary[name] = "[changed]"
        else:
            summary[name] = _safe_value(value)
    return summary


def record_event(*, organization, action, entity, actor=None, request=None, summary=None):
    """Write one audit row. Call inside the same transaction as the change it describes."""
    entity_type = entity._meta.label_lower if isinstance(entity, models.Model) else str(entity)
    entity_id = str(entity.pk) if isinstance(entity, models.Model) else ""
    if actor is None and request is not None and getattr(request.user, "is_authenticated", False):
        actor = request.user
    return AuditEvent.objects.create(
        organization=organization,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary or {},
        request_id=(get_request_id(request) if request is not None else "") or "",
    )
