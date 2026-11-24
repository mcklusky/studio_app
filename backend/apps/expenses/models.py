import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.currencies.models import Currency
from apps.organizations.models import Branch, BusinessSection, Organization
from apps.payments.models import PaymentMethod


class ExpenseCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="expense_categories")
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "name"], name="uniq_expense_category_per_org")]

    def __str__(self):
        return self.name


class Expense(models.Model):
    """An operating expense, posted when recorded. Corrections are reversals, never edits."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="expenses")
    number = models.CharField(max_length=20)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, related_name="expenses")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="expenses")
    expense_date = models.DateField()
    description = models.CharField(max_length=240)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_units_per_usd = models.DecimalField(max_digits=16, decimal_places=6)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8)
    fx_rate_date = models.DateField(null=True, blank=True)
    base_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_expenses")
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_expenses"
    )
    reversal_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-expense_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_expense_number_per_org"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_positive"),
        ]
        indexes = [models.Index(fields=["organization", "-expense_date"], name="expense_org_date_idx")]

    def __str__(self):
        return self.number
