"""Department (custom) orders: photography bookings, printing jobs and custom clothing.

One shared CustomOrder row holds the commercial and workflow fields (customer,
price, FX snapshot, deposit/balance, due date, assignee, status). A one-to-one
detail row holds what is specific to each department. Orders never move stock
on their own (REQ-025); materials are consumed explicitly through OrderMaterial.
"""

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


class OrderKind(models.TextChoices):
    PHOTOGRAPHY = "photography", "Photography booking"
    PRINTING = "printing", "Printing job"
    CLOTHING = "clothing", "Custom clothing"


# Workflow steps per department, in order. "cancelled" is outside the flow.
STATUS_FLOWS = {
    OrderKind.PHOTOGRAPHY: ["booked", "shoot_done", "editing", "ready", "delivered"],
    OrderKind.PRINTING: ["pending", "designing", "production", "completed", "delivered"],
    OrderKind.CLOTHING: ["pending", "designing", "production", "completed", "delivered"],
}
STATUS_LABELS = {
    "booked": "Booked",
    "shoot_done": "Shoot done",
    "editing": "Editing",
    "ready": "Ready for delivery",
    "pending": "Pending",
    "designing": "Designing",
    "production": "In production",
    "completed": "Completed",
    "delivered": "Delivered",
    "cancelled": "Cancelled",
}
CLOSED_STATUSES = ("delivered", "cancelled")


class CustomOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="custom_orders")
    number = models.CharField(max_length=20)
    kind = models.CharField(max_length=20, choices=OrderKind.choices)
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, related_name="custom_orders")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="custom_orders")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="custom_orders")
    title = models.CharField(max_length=160)
    status = models.CharField(max_length=20)

    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_units_per_usd = models.DecimalField(max_digits=16, decimal_places=6)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8)
    fx_rate_date = models.DateField(null=True, blank=True)
    # Agreed selling price, in the order currency. Named `total` so payments treat orders like invoices.
    total = models.DecimalField(**MONEY)
    base_total = models.DecimalField(**MONEY)
    production_cost = models.DecimalField(**MONEY, null=True, blank=True, help_text="Estimated outside/production cost, order currency.")
    # Cached from payment allocations; only apps.payments.services changes it, under a row lock.
    paid_amount = models.DecimalField(**MONEY, default=Decimal("0"))

    due_date = models.DateField()
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="assigned_orders"
    )
    notes = models.TextField(blank=True, max_length=2000)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_orders")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="cancelled_orders"
    )
    cancel_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["due_date", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_order_number_per_org"),
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_non_negative"),
            models.CheckConstraint(condition=Q(production_cost__isnull=True) | Q(production_cost__gte=0), name="order_cost_non_negative"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0) & Q(paid_amount__lte=F("total")), name="order_paid_within_total"),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="order_org_status_idx"),
            models.Index(fields=["organization", "due_date"], name="order_org_due_idx"),
            models.Index(fields=["organization", "customer"], name="order_org_customer_idx"),
        ]

    @property
    def flow(self):
        return STATUS_FLOWS[self.kind]

    @property
    def is_open(self):
        return self.status not in CLOSED_STATUSES

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def balance_due(self):
        return Decimal("0") if self.status == "cancelled" else self.total - self.paid_amount

    def __str__(self):
        return self.number


class PhotographyDetail(models.Model):
    order = models.OneToOneField(CustomOrder, on_delete=models.CASCADE, primary_key=True, related_name="photography")
    shoot_type = models.CharField(max_length=80, help_text="Wedding, portrait, event, product…")
    package = models.CharField(max_length=80, blank=True)
    shoot_at = models.DateTimeField()
    location = models.CharField(max_length=160, blank=True)
    photos_promised = models.PositiveIntegerField(null=True, blank=True)


class PrintingDetail(models.Model):
    order = models.OneToOneField(CustomOrder, on_delete=models.CASCADE, primary_key=True, related_name="printing")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    item = models.CharField(max_length=120, help_text="Banner, flyers, business cards…")
    quantity = models.DecimalField(**QTY)
    size = models.CharField(max_length=60, blank=True)
    material = models.CharField(max_length=80, blank=True)
    design = models.TextField(blank=True, max_length=2000)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="printing_quantity_positive")]


class ClothingDetail(models.Model):
    order = models.OneToOneField(CustomOrder, on_delete=models.CASCADE, primary_key=True, related_name="clothing")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    item = models.CharField(max_length=120, help_text="Jersey, T-shirt, uniform…")
    color = models.CharField(max_length=60, blank=True)
    design = models.TextField(blank=True, max_length=2000)


class ClothingItem(models.Model):
    """One size/name/number line of a clothing order (e.g. one player's jersey)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(CustomOrder, on_delete=models.CASCADE, related_name="clothing_items")
    size = models.CharField(max_length=20)
    custom_name = models.CharField(max_length=40, blank=True)
    custom_number = models.CharField(max_length=10, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="clothing_item_quantity_positive")]


class OrderStatusEvent(models.Model):
    """Append-only history of status changes, including corrections."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(CustomOrder, on_delete=models.CASCADE, related_name="status_events")
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    note = models.CharField(max_length=240, blank=True)
    is_correction = models.BooleanField(default=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("Order status history is append-only.")
        super().save(*args, **kwargs)


class OrderMaterial(models.Model):
    """Stock explicitly used for an order (blank shirts, paper, vinyl…). Creates a stock movement."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(CustomOrder, on_delete=models.PROTECT, related_name="materials")
    variant = models.ForeignKey(ProductVariant, on_delete=models.PROTECT, related_name="order_materials")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(**QTY)
    unit_cost_base = models.DecimalField(max_digits=14, decimal_places=4)
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="order_material")
    reversal_movement = models.OneToOneField(
        StockMovement, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_order_material"
    )
    note = models.CharField(max_length=240, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reversal_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0), name="order_material_quantity_positive")]
