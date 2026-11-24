"""Manual customer and supplier payments (money received/paid outside the system).

Rules (REQ-008, REQ-011, REQ-012):
* A payment is in one currency and settles obligations in that same currency only.
  (Cross-currency settlement is an open accounting decision.)
* It is allocated to specific invoices/purchases, or oldest-first when none are given.
* It can never exceed what is owed: no overpayment or customer credit in the MVP.
* Corrections are reversals with a reason; nothing is edited or deleted.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_event
from apps.common.exceptions import Conflict
from apps.common.numbering import next_number
from apps.currencies.services import FxSnapshot, snapshot_for
from apps.payments.models import CustomerPayment, CustomerPaymentAllocation, PaymentMethod, SupplierPayment, SupplierPaymentAllocation

CENTS = Decimal("0.01")


def validate_payment_input(amount, method, amount_tendered=None):
    amount = Decimal(amount).quantize(CENTS)
    if amount <= 0:
        raise ValidationError({"payment.amount": ["Enter an amount greater than zero."]})
    if method not in PaymentMethod.values:
        raise ValidationError({"payment.method": ["Choose a payment method."]})
    if amount_tendered is not None:
        amount_tendered = Decimal(amount_tendered).quantize(CENTS)
        if method != PaymentMethod.CASH:
            raise ValidationError({"payment.amount_tendered": ["Cash tendered only applies to cash payments."]})
        if amount_tendered < amount:
            raise ValidationError({"payment.amount_tendered": ["Cash tendered cannot be less than the amount paid."]})
    return amount, amount_tendered


def _plan_allocations(open_docs, amount, requested, label):
    """Return [(doc, amount)] using the requested split, or oldest-first across open_docs.

    open_docs: locked documents (oldest first) with .pk, .number, .total and .paid_amount.
    requested: None, or {doc_id: amount}.
    """
    by_id = {str(doc.pk): doc for doc in open_docs}
    plan = []
    if requested:
        total = Decimal("0")
        for doc_id, value in requested.items():
            doc = by_id.get(str(doc_id))
            value = Decimal(value).quantize(CENTS)
            if doc is None:
                raise ValidationError({f"allocations.{doc_id}": [f"Choose an open {label} for this payment's currency."]})
            if value <= 0:
                continue
            due = doc.total - doc.paid_amount
            if value > due:
                raise ValidationError({f"allocations.{doc_id}": [f"{doc.number} only has {due} due."]})
            plan.append((doc, value))
            total += value
        if total != amount:
            raise ValidationError({"allocations": [f"Allocations add up to {total}, but the payment is {amount}."]})
        return plan
    owed = sum((doc.total - doc.paid_amount for doc in open_docs), Decimal("0"))
    if amount > owed:
        raise ValidationError({"amount": [f"Only {owed} is owed in this currency; a payment cannot exceed it."]})
    remaining = amount
    for doc in open_docs:
        if remaining <= 0:
            break
        take = min(remaining, doc.total - doc.paid_amount)
        if take > 0:
            plan.append((doc, take))
            remaining -= take
    return plan


def _apply(plan, sign):
    for doc, value in plan:
        type(doc).objects.filter(pk=doc.pk).update(paid_amount=F("paid_amount") + sign * value)


# ---------- customers ----------


def _doc_date(doc):
    return doc.posted_at if hasattr(doc, "posted_at") else doc.created_at


def _lock_open_customer_documents(organization, customer, currency, targets):
    """Lock and return open sales and department orders (oldest first) this payment may settle.

    targets: None for all of the customer's open documents, or an explicit list of
    Sale / CustomOrder instances (already scope-checked by the caller).
    """
    from apps.orders.models import CustomOrder
    from apps.sales.models import Sale

    sales = Sale.objects.select_for_update().filter(
        organization=organization, status=Sale.Status.POSTED, currency=currency, paid_amount__lt=F("total")
    )
    orders = (
        CustomOrder.objects.select_for_update()
        .filter(organization=organization, currency=currency, paid_amount__lt=F("total"))
        .exclude(status="cancelled")
    )
    if targets is None:
        sales, orders = sales.filter(customer=customer), orders.filter(customer=customer)
    else:
        sales = sales.filter(pk__in=[d.pk for d in targets if isinstance(d, Sale)])
        orders = orders.filter(pk__in=[d.pk for d in targets if isinstance(d, CustomOrder)])
    return sorted([*sales, *orders], key=_doc_date)


def _allocation(payment, doc, value):
    from apps.sales.models import Sale

    if isinstance(doc, Sale):
        return CustomerPaymentAllocation(payment=payment, sale=doc, amount=value)
    return CustomerPaymentAllocation(payment=payment, custom_order=doc, amount=value)


def receive_customer_payment(
    *,
    organization,
    customer,
    currency,
    amount,
    method,
    actor,
    reference="",
    amount_tendered=None,
    allocations=None,
    request=None,
    targets=None,
):
    """Record money received from a customer and allocate it to open sales and orders."""
    amount, amount_tendered = validate_payment_input(amount, method, amount_tendered)
    with transaction.atomic():
        open_docs = _lock_open_customer_documents(organization, customer, currency, targets)
        plan = _plan_allocations(open_docs, amount, allocations, "invoice or order")
        if not plan:
            raise ValidationError({"amount": ["There is nothing owed in this currency."]})
        fx = snapshot_for(organization, currency, timezone.localdate())
        payment = CustomerPayment.objects.create(
            organization=organization,
            number=next_number(organization, "PAY"),
            customer=customer,
            method=method,
            reference=(reference or "")[:80],
            amount=amount,
            amount_tendered=amount_tendered,
            currency=currency,
            fx_units_per_usd=fx.units_per_usd,
            fx_rate_to_base=fx.rate_to_base,
            fx_rate_date=fx.rate_date,
            base_amount=fx.to_base(amount),
            received_at=timezone.now(),
            created_by=actor,
        )
        CustomerPaymentAllocation.objects.bulk_create([_allocation(payment, doc, value) for doc, value in plan])
        _apply(plan, 1)
        record_event(
            organization=organization,
            action="payment.received",
            entity=payment,
            actor=actor,
            request=request,
            summary={
                "amount": str(amount),
                "currency": currency,
                "method": method,
                "allocations": {doc.number: str(value) for doc, value in plan},
            },
        )
        return payment


def _pay_document(doc, *, is_open, closed_message, amount, method, actor, reference="", amount_tendered=None, request=None):
    model = type(doc)
    if not is_open(doc):
        raise Conflict(closed_message)
    amount_q = Decimal(amount).quantize(CENTS)
    with transaction.atomic():
        current = model.objects.select_for_update().get(pk=doc.pk)
        if not is_open(current):
            raise Conflict(closed_message)
        due = current.total - current.paid_amount
        if amount_q > due:
            raise ValidationError({"payment.amount": [f"The balance due is {current.currency} {due}; payment cannot exceed it."]})
        payment = receive_customer_payment(
            organization=current.organization,
            customer=current.customer,
            currency=current.currency,
            amount=amount,
            method=method,
            actor=actor,
            reference=reference,
            amount_tendered=amount_tendered,
            request=request,
            targets=[current],
        )
    doc.refresh_from_db(fields=["paid_amount"])
    return payment


def pay_sale(sale, *, amount, method, actor, reference="", amount_tendered=None, request=None):
    """Record a payment against one sale (checkout and the sale screen)."""
    return _pay_document(
        sale,
        is_open=lambda s: s.status == "posted",
        closed_message="This sale has been reversed; payments cannot be added.",
        amount=amount,
        method=method,
        actor=actor,
        reference=reference,
        amount_tendered=amount_tendered,
        request=request,
    )


def pay_order(order, *, amount, method, actor, reference="", amount_tendered=None, request=None):
    """Record a deposit or payment against one department order."""
    return _pay_document(
        order,
        is_open=lambda o: o.status != "cancelled",
        closed_message="This order has been cancelled; payments cannot be added.",
        amount=amount,
        method=method,
        actor=actor,
        reference=reference,
        amount_tendered=amount_tendered,
        request=request,
    )


@transaction.atomic
def reverse_customer_payment(payment, *, actor, reason, request=None, cascade_from=None):
    """Undo a payment recorded in error: its allocations stop counting and balances reopen.

    cascade_from: the sale being reversed; its own allocation is skipped here.
    """
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why this payment is being reversed."]})
    payment = CustomerPayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != CustomerPayment.Status.POSTED:
        raise Conflict("This payment has already been reversed.")
    plan = [
        (a.target, a.amount)
        for a in payment.allocations.select_related("sale", "custom_order")
        if cascade_from is None or a.target_id != cascade_from.pk
    ]
    _apply(plan, -1)
    payment.status = CustomerPayment.Status.REVERSED
    payment.reversed_at = timezone.now()
    payment.reversed_by = actor
    payment.reversal_reason = reason.strip()[:240]
    payment.save(update_fields=["status", "reversed_at", "reversed_by", "reversal_reason"])
    if cascade_from is None:
        record_event(
            organization=payment.organization,
            action="payment.reversed",
            entity=payment,
            actor=actor,
            request=request,
            summary={"number": payment.number, "amount": str(payment.amount), "reason": payment.reversal_reason},
        )
    return payment


def reverse_payments_for_sale(sale, *, actor, reason):
    """A reversed sale refunds only its own share of each payment.

    A payment that also covered other invoices/orders is reversed and re-issued
    (same date, method and reference) for those other documents, so their
    balances do not change and the cash record shows exactly the refunded part.
    """
    for allocation in CustomerPaymentAllocation.objects.filter(sale=sale, payment__status=CustomerPayment.Status.POSTED):
        original = allocation.payment
        others = list(original.allocations.exclude(sale=sale).select_related("sale", "custom_order"))
        reverse_customer_payment(original, actor=actor, reason=f"Sale {sale.number} reversed: {reason}", cascade_from=sale)
        if others:
            remainder = sum((a.amount for a in others), Decimal("0"))
            replacement = CustomerPayment.objects.create(
                organization=original.organization,
                number=next_number(original.organization, "PAY"),
                customer=original.customer,
                method=original.method,
                reference=original.reference,
                amount=remainder,
                currency=original.currency,
                fx_units_per_usd=original.fx_units_per_usd,
                fx_rate_to_base=original.fx_rate_to_base,
                fx_rate_date=original.fx_rate_date,
                base_amount=FxSnapshot(original.currency, original.fx_units_per_usd, original.fx_rate_date).to_base(remainder),
                received_at=original.received_at,
                created_by=actor,
            )
            CustomerPaymentAllocation.objects.bulk_create([_allocation(replacement, a.target, a.amount) for a in others])
            _apply([(a.target, a.amount) for a in others], 1)
            record_event(
                organization=original.organization,
                action="payment.reissued",
                entity=replacement,
                actor=actor,
                summary={"replaces": original.number, "amount": str(remainder), "after_sale_reversal": sale.number},
            )


# ---------- suppliers ----------


@transaction.atomic
def pay_supplier(
    *, organization, supplier, currency, amount, method, actor, reference="", paid_on=None, allocations=None, request=None, section_ids=None
):
    """Record money paid to a supplier and allocate it to their open purchases."""
    from apps.purchasing.models import Purchase

    amount, _ = validate_payment_input(amount, method)
    paid_on = paid_on or timezone.localdate()
    if paid_on > timezone.localdate():
        raise ValidationError({"paid_on": ["Payment date cannot be in the future."]})
    open_purchases = list(
        Purchase.objects.select_for_update()
        .filter(organization=organization, supplier=supplier, currency=currency, paid_amount__lt=F("total"))
        .exclude(status=Purchase.Status.CANCELLED)
        .filter(**({"section_id__in": section_ids} if section_ids is not None else {}))
        .order_by("purchase_date", "created_at")
    )
    plan = _plan_allocations(open_purchases, amount, allocations, "purchase")
    if not plan:
        raise ValidationError({"amount": ["Nothing is owed to this supplier in this currency."]})
    fx = snapshot_for(organization, currency, paid_on)
    payment = SupplierPayment.objects.create(
        organization=organization,
        number=next_number(organization, "SP"),
        supplier=supplier,
        method=method,
        reference=(reference or "")[:80],
        amount=amount,
        currency=currency,
        fx_units_per_usd=fx.units_per_usd,
        fx_rate_to_base=fx.rate_to_base,
        fx_rate_date=fx.rate_date,
        base_amount=fx.to_base(amount),
        paid_on=paid_on,
        created_by=actor,
    )
    SupplierPaymentAllocation.objects.bulk_create(
        [SupplierPaymentAllocation(payment=payment, purchase=purchase, amount=value) for purchase, value in plan]
    )
    _apply(plan, 1)
    record_event(
        organization=organization,
        action="supplier_payment.created",
        entity=payment,
        actor=actor,
        request=request,
        summary={"amount": str(amount), "currency": currency, "method": method, "allocations": {p.number: str(value) for p, value in plan}},
    )
    return payment


@transaction.atomic
def reverse_supplier_payment(payment, *, actor, reason, request=None):
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why this payment is being reversed."]})
    payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
    if payment.status != SupplierPayment.Status.POSTED:
        raise Conflict("This payment has already been reversed.")
    _apply([(a.purchase, a.amount) for a in payment.allocations.select_related("purchase")], -1)
    payment.status = SupplierPayment.Status.REVERSED
    payment.reversed_at = timezone.now()
    payment.reversed_by = actor
    payment.reversal_reason = reason.strip()[:240]
    payment.save(update_fields=["status", "reversed_at", "reversed_by", "reversal_reason"])
    record_event(
        organization=payment.organization,
        action="supplier_payment.reversed",
        entity=payment,
        actor=actor,
        request=request,
        summary={"number": payment.number, "amount": str(payment.amount), "reason": payment.reversal_reason},
    )
    return payment
