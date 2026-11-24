import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.organizations.models import Branch, BusinessSection, Organization


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
    class Currency(models.TextChoices):
        LRD = "LRD", "Liberian Dollar"
        USD = "USD", "US Dollar"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, related_name="expenses")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, null=True, blank=True, related_name="expenses")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8, validators=[MinValueValidator(0.00000001)])
    base_amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(0)])
    occurred_at = models.DateTimeField()
    description = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recorded_expenses")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [models.Index(fields=["organization", "occurred_at"], name="expense_org_date_idx")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.currency == self.Currency.USD and self.fx_rate_to_base != 1:
            raise ValidationError({"fx_rate_to_base": "USD base-currency transactions must use an FX rate of 1."})
        if self.section_id and self.organization_id and self.section.organization_id != self.organization_id:
            raise ValidationError({"section": "Section must belong to the expense organization."})
        if self.category_id and self.organization_id and self.category.organization_id != self.organization_id:
            raise ValidationError({"category": "Category must belong to the expense organization."})
        if self.branch_id and self.organization_id and self.branch.organization_id != self.organization_id:
            raise ValidationError({"branch": "Branch must belong to the expense organization."})


