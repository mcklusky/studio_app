import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.organizations.models import Organization


class Currency(models.TextChoices):
    """Transaction currencies. USD is the reporting (base) currency."""

    USD = "USD", "US Dollar"
    LRD = "LRD", "Liberian Dollar"


class ExchangeRate(models.Model):
    """Owner/admin-entered daily rate: how many units of `currency` buy 1 USD.

    Append-only. A later entry for the same date supersedes an earlier one;
    posted transactions keep their own snapshot, so nothing posted ever changes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="exchange_rates")
    currency = models.CharField(max_length=3, choices=Currency.choices)
    units_per_usd = models.DecimalField(max_digits=16, decimal_places=6, validators=[MinValueValidator(0.000001)])
    effective_date = models.DateField()
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="exchange_rates")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_date", "-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(units_per_usd__gt=0), name="exchange_rate_positive"),
            models.CheckConstraint(condition=~Q(currency="USD"), name="exchange_rate_not_base"),
        ]
        indexes = [models.Index(fields=["organization", "currency", "-effective_date"], name="fx_org_currency_date_idx")]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Exchange rates are append-only; enter a new rate instead.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Exchange rates are append-only.")
