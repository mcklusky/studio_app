import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import ProductVariant
from apps.organizations.models import Branch, Organization

QTY = {"max_digits": 12, "decimal_places": 3}
COST = {"max_digits": 14, "decimal_places": 4}


class StockBalance(models.Model):
    """Current on-hand quantity and moving weighted-average cost per variant and branch.

    A cache of the movement ledger: only apps.inventory.services may change it,
    always under a row lock, in the same transaction as the movement it reflects.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stock_balances")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="stock_balances")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="stock_balances")
    quantity = models.DecimalField(**QTY, default=Decimal("0"))
    average_cost_base = models.DecimalField(**COST, default=Decimal("0"))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["variant", "branch"], name="uniq_stock_balance_variant_branch"),
            models.CheckConstraint(condition=Q(quantity__gte=0), name="stock_balance_quantity_non_negative"),
            models.CheckConstraint(condition=Q(average_cost_base__gte=0), name="stock_balance_cost_non_negative"),
        ]


class StockMovement(models.Model):
    """Append-only ledger entry. Corrections are new movements, never edits."""

    class Type(models.TextChoices):
        OPENING = "opening", "Opening balance"
        ADJUSTMENT = "adjustment", "Adjustment"
        RECEIPT = "receipt", "Purchase receipt"
        RECEIPT_REVERSAL = "receipt_reversal", "Receipt reversal"
        SALE = "sale", "Sale"
        SALE_REVERSAL = "sale_reversal", "Sale reversal"
        ORDER_CONSUMPTION = "order_consumption", "Order material use"
        ORDER_RETURN = "order_return", "Order material returned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stock_movements")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="stock_movements")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=30, choices=Type.choices)
    quantity_delta = models.DecimalField(**QTY)
    unit_cost_base = models.DecimalField(**COST)
    quantity_after = models.DecimalField(**QTY)
    average_cost_after = models.DecimalField(**COST)
    source_type = models.CharField(max_length=80, blank=True)
    source_id = models.CharField(max_length=64, blank=True)
    reason = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(quantity_delta=0), name="stock_movement_delta_non_zero"),
            models.CheckConstraint(condition=Q(quantity_after__gte=0), name="stock_movement_after_non_negative"),
            models.CheckConstraint(condition=Q(unit_cost_base__gte=0), name="stock_movement_cost_non_negative"),
        ]
        indexes = [
            models.Index(fields=["organization", "variant", "-created_at"], name="stock_move_variant_idx"),
            models.Index(fields=["organization", "source_type", "source_id"], name="stock_move_source_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Stock movements are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Stock movements are append-only.")


class StockAdjustment(models.Model):
    """A reasoned manual change to stock (opening count, damage, loss, correction...)."""

    class Reason(models.TextChoices):
        OPENING = "opening", "Opening stock"
        COUNT = "count_correction", "Stock count correction"
        DAMAGE = "damage", "Damaged"
        LOSS = "loss", "Lost or stolen"
        RETURN = "customer_return", "Customer return"
        OTHER = "other", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="stock_adjustments")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="stock_adjustments")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="stock_adjustments")
    reason = models.CharField(max_length=30, choices=Reason.choices)
    note = models.CharField(max_length=240, blank=True)
    quantity_delta = models.DecimalField(**QTY)
    unit_cost_base = models.DecimalField(**COST, null=True, blank=True)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="adjustment")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_adjustments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.CheckConstraint(condition=~Q(quantity_delta=0), name="stock_adjustment_delta_non_zero")]
