import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.catalog.models import Customer
from apps.currencies.models import Currency
from apps.organizations.models import Organization

MONEY = {"max_digits": 14, "decimal_places": 2}


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    MOBILE_MONEY = "mobile_money", "Mobile money"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    CARD = "card", "Card"
    OTHER = "other", "Other"


class CustomerPayment(models.Model):
    """Money received from a customer outside the system (MVP records it; no live collection)."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="customer_payments")
    number = models.CharField(max_length=20)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(**MONEY)
    amount_tendered = models.DecimalField(**MONEY, null=True, blank=True, help_text="Cash handed over; change = tendered - amount.")
    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_units_per_usd = models.DecimalField(max_digits=16, decimal_places=6)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8)
    fx_rate_date = models.DateField(null=True, blank=True)
    base_amount = models.DecimalField(**MONEY)
    received_at = models.DateTimeField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="customer_payments")
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_customer_payments"
    )
    reversal_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-received_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_customer_payment_number"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="customer_payment_positive"),
            models.CheckConstraint(
                condition=Q(amount_tendered__isnull=True) | Q(amount_tendered__gte=models.F("amount")),
                name="customer_payment_tendered_covers_amount",
            ),
        ]
        indexes = [models.Index(fields=["organization", "-received_at"], name="cust_payment_org_date_idx")]


class CustomerPaymentAllocation(models.Model):
    """How much of a payment settles which obligation: exactly one sale or one department order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(CustomerPayment, on_delete=models.PROTECT, related_name="allocations")
    sale = models.ForeignKey("sales.Sale", on_delete=models.PROTECT, null=True, blank=True, related_name="allocations")
    custom_order = models.ForeignKey("orders.CustomOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="allocations")
    amount = models.DecimalField(**MONEY)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_allocation_positive"),
            models.CheckConstraint(
                condition=(Q(sale__isnull=False) & Q(custom_order__isnull=True)) | (Q(sale__isnull=True) & Q(custom_order__isnull=False)),
                name="payment_allocation_one_target",
            ),
        ]

    @property
    def target(self):
        return self.sale if self.sale_id else self.custom_order

    @property
    def target_id(self):
        return self.sale_id or self.custom_order_id

    @property
    def target_kind(self):
        return "sale" if self.sale_id else "order"


class SupplierPayment(models.Model):
    """Money paid to a supplier outside the system, allocated to purchases."""

    class Status(models.TextChoices):
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="supplier_payments")
    number = models.CharField(max_length=20)
    supplier = models.ForeignKey("catalog.Supplier", on_delete=models.PROTECT, related_name="payments")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.POSTED)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    reference = models.CharField(max_length=80, blank=True)
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, choices=Currency.choices)
    fx_units_per_usd = models.DecimalField(max_digits=16, decimal_places=6)
    fx_rate_to_base = models.DecimalField(max_digits=16, decimal_places=8)
    fx_rate_date = models.DateField(null=True, blank=True)
    base_amount = models.DecimalField(**MONEY)
    paid_on = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="supplier_payments")
    created_at = models.DateTimeField(auto_now_add=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_supplier_payments"
    )
    reversal_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-paid_on", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "number"], name="uniq_supplier_payment_number"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="supplier_payment_positive"),
        ]


class SupplierPaymentAllocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(SupplierPayment, on_delete=models.PROTECT, related_name="allocations")
    purchase = models.ForeignKey("purchasing.Purchase", on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(**MONEY)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="supplier_allocation_positive")]
