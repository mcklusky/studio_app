import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.catalog.models import ProductVariant, Supplier
from apps.currencies.models import Currency
from apps.inventory.models import StockMovement
from apps.organizations.models import Branch, BusinessSection, Organization

MONEY = {"max_digits": 14, "decimal_places": 2}
QTY = {"max_digits": 12, "decimal_places": 3}


class Purchase(models.Model):
    """A supplier purchase. Lines are editable only while nothing has been received."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTIAL = "partially_received", "Partially received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="purchases")
    number = models.CharField(max_length=20)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, related_name="purchases")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="purchases")
    purchase_date = models.DateField()
    supplier_reference = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    # Amounts in the transaction currency, with an immutable FX snapshot taken at creation.
    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_units_per_usd = models.DecimalField(max_digits=16, decimal_places=6)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8)
    fx_rate_date = models.DateField(null=True, blank=True)
    shipping_cost = models.DecimalField(**MONEY, default=Decimal("0"))
    other_cost = models.DecimalField(**MONEY, default=Decimal("0"))
    subtotal = models.DecimalField(**MONEY, default=Decimal("0"))
    total = models.DecimalField(**MONEY, default=Decimal("0"))
    base_total = models.DecimalField(**MONEY, default=Decimal("0"))
    # Cached from supplier payment allocations; only apps.payments.services changes it, under a row lock.
    paid_amount = models.DecimalField(**MONEY, default=Decimal("0"))

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchases")
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="cancelled_purchases"
    )
    cancel_reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchase_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_purchase_number_per_org"),
            models.CheckConstraint(condition=Q(shipping_cost__gte=0) & Q(other_cost__gte=0), name="purchase_extra_costs_non_negative"),
            models.CheckConstraint(condition=Q(fx_units_per_usd__gt=0), name="purchase_fx_positive"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0) & Q(paid_amount__lte=F("total")), name="purchase_paid_within_total"),
        ]
        indexes = [models.Index(fields=["organization", "status", "-purchase_date"], name="purchase_org_status_idx")]

    @property
    def balance_due(self):
        return Decimal("0") if self.status == self.Status.CANCELLED else self.total - self.paid_amount

    def __str__(self):
        return self.number


class PurchaseLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="purchase_lines")
    description = models.CharField(max_length=200)
    quantity = models.DecimalField(**QTY)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=4)
    line_total = models.DecimalField(**MONEY)
    quantity_received = models.DecimalField(**QTY, default=Decimal("0"))
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="purchase_line_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name="purchase_line_cost_non_negative"),
            models.CheckConstraint(
                condition=Q(quantity_received__gte=0) & Q(quantity_received__lte=F("quantity")),
                name="purchase_line_received_within_ordered",
            ),
        ]

    @property
    def quantity_outstanding(self):
        return self.quantity - self.quantity_received


class GoodsReceipt(models.Model):
    """One delivery against a purchase. Reversal removes its stock with an audited reason."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="goods_receipts")
    purchase = models.ForeignKey(Purchase, on_delete=models.PROTECT, related_name="receipts")
    number = models.CharField(max_length=20)
    received_date = models.DateField()
    note = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="goods_receipts")
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_goods_receipts"
    )
    reversal_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["organization", "number"], name="uniq_goods_receipt_number_per_org")]


class GoodsReceiptLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="lines")
    purchase_line = models.ForeignKey(PurchaseLine, on_delete=models.PROTECT, related_name="receipt_lines")
    quantity = models.DecimalField(**QTY)
    landed_unit_cost = models.DecimalField(
        max_digits=14, decimal_places=4, help_text="Transaction currency, incl. allocated shipping/other."
    )
    landed_unit_cost_base = models.DecimalField(max_digits=14, decimal_places=4)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="receipt_line")
    reversal_movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_receipt_line"
    )

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="receipt_line_quantity_positive")]
