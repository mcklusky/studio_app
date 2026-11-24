from django.conf import settings
from django.db import models

from apps.organizations.models import Organization


class AlertRead(models.Model):
    """That a person has seen one alert.

    Alerts themselves are computed live from current data (apps/notifications/services.py),
    so they are always up to date and disappear when resolved. Each alert key
    includes the state that matters (e.g. a due date), so a changed situation
    shows up as unread again.
    """

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_reads")
    key = models.CharField(max_length=160)
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "user", "key"], name="uniq_alert_read")]
