import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.catalog.models import Customer, Product, ProductVariant
from apps.currencies.models import Currency
from apps.inventory.models import StockMovement
from apps.organizations.models import Branch, BusinessSection, Organization

MONEY = {"max_digits": 14, "decimal_places": 2}
QTY = {"max_digits": 12, "decimal_places": 3}


class Sale(models.Model):
    """A posted sale. Lines, totals and FX snapshot never change; corrections are reversals."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="sales")
    number = models.CharField(max_length=20)
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, related_name="sales")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="sales")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True, related_name="sales")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)

    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_units_per_usd = models.DecimalField(max_digits=16, decimal_places=6)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8)
    fx_rate_date = models.DateField(null=True, blank=True)

    subtotal = models.DecimalField(**MONEY)
    line_discount_total = models.DecimalField(**MONEY, default=Decimal("0"))
    sale_discount = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY)
    base_total = models.DecimalField(**MONEY)
    cost_total_base = models.DecimalField(max_digits=16, decimal_places=4, default=Decimal("0"))
    # Cached from payment allocations; only apps.payments.services changes it, under a row lock.
    paid_amount = models.DecimalField(**MONEY, default=Decimal("0"))

    notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    posted_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_sales"
    )
    reversal_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-posted_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_sale_number_per_org"),
            models.CheckConstraint(condition=Q(total__gte=0) & Q(sale_discount__gte=0), name="sale_amounts_non_negative"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0) & Q(paid_amount__lte=F("total")), name="sale_paid_within_total"),
        ]
        indexes = [
            models.Index(fields=["organization", "-posted_at"], name="sale_org_posted_idx"),
            models.Index(fields=["organization", "section", "-posted_at"], name="sale_org_section_idx"),
            models.Index(fields=["organization", "customer"], name="sale_org_customer_idx"),
        ]

    @property
    def discount_total(self):
        return self.line_discount_total + self.sale_discount

    @property
    def balance_due(self):
        return Decimal("0") if self.status == self.Status.REVERSED else self.total - self.paid_amount

    def __str__(self):
        return self.number


class SaleLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="sale_lines")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, null=True, blank=True, related_name="sale_lines")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(**QTY)
    unit_price = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY, default=Decimal("0"))
    line_total = models.DecimalField(**MONEY)
    price_overridden = models.BooleanField(default=False)
    # Cost at the moment of sale (weighted average), for gross profit. Null for untracked items.
    unit_cost_base = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="sale_line")
    reversal_movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_sale_line"
    )
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="sale_line_quantity_positive"),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0) & Q(discount__gte=0) & Q(line_total__gte=0), name="sale_line_amounts_non_negative"
            ),
        ]
