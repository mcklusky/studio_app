"""Department order workflow.

Rules:
* An order belongs to one section; its department type comes from the section
  (photography / printing / clothing). Other sections do not take orders.
* The price and FX snapshot are fixed at creation in the chosen currency; an
  authorized edit may change the price but never below what has been paid.
* Status moves forward through the department's steps (skipping is allowed).
  Moving backwards is a correction: it needs orders.manage and a note.
* Delivered and cancelled orders are closed. Cancelling needs orders.manage,
  a reason, and no payments still applied (reverse them first).
* Orders never touch stock unless materials are recorded explicitly.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import record_event
from apps.common.exceptions import Conflict
from apps.common.numbering import next_number
from apps.currencies.services import FxSnapshot, snapshot_for
from apps.identity.scope import has_permission
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement
from apps.orders.models import (
    CLOSED_STATUSES,
    STATUS_FLOWS,
    STATUS_LABELS,
    ClothingDetail,
    ClothingItem,
    CustomOrder,
    OrderKind,
    OrderMaterial,
    OrderStatusEvent,
    PhotographyDetail,
    PrintingDetail,
)
from apps.payments.services import pay_order, validate_payment_input

CENTS = Decimal("0.01")
DETAIL_MODELS = {OrderKind.PHOTOGRAPHY: PhotographyDetail, OrderKind.PRINTING: PrintingDetail, OrderKind.CLOTHING: ClothingDetail}


def kind_for_section(section):
    if section.code not in OrderKind.values:
        raise ValidationError({"section": [f"{section.name} does not take department orders."]})
    return OrderKind(section.code)


def _money(value):
    return Decimal(value).quantize(CENTS)


def _event(order, from_status, to_status, actor, note="", correction=False):
    OrderStatusEvent.objects.create(
        order=order, from_status=from_status, to_status=to_status, actor=actor, note=(note or "")[:240], is_correction=correction
    )


def _save_detail(order, detail, items):
    model = DETAIL_MODELS[order.kind]
    model.objects.update_or_create(order=order, defaults=detail)
    if order.kind == OrderKind.CLOTHING and items is not None:
        order.clothing_items.all().delete()
        ClothingItem.objects.bulk_create([ClothingItem(order=order, position=i, **item) for i, item in enumerate(items)])


@transaction.atomic
def create_order(
    *,
    membership,
    actor,
    section,
    branch,
    customer,
    currency,
    total,
    due_date,
    title,
    detail,
    items=None,
    assigned_to=None,
    production_cost=None,
    notes="",
    deposit=None,
    request=None,
):
    organization = membership.organization
    kind = kind_for_section(section)
    total = _money(total)
    if total < 0:
        raise ValidationError({"total": ["Price cannot be negative."]})
    if deposit:
        validate_payment_input(deposit["amount"], deposit["method"], deposit.get("amount_tendered"))
        if _money(deposit["amount"]) > total:
            raise ValidationError({"deposit.amount": ["The deposit cannot be more than the price."]})
    fx = snapshot_for(organization, currency, timezone.localdate())
    order = CustomOrder.objects.create(
        organization=organization,
        number=next_number(organization, "ORD"),
        kind=kind,
        section=section,
        branch=branch,
        customer=customer,
        title=title.strip(),
        status=STATUS_FLOWS[kind][0],
        currency=currency,
        fx_units_per_usd=fx.units_per_usd,
        fx_rate_to_base=fx.rate_to_base,
        fx_rate_date=fx.rate_date,
        total=total,
        base_total=fx.to_base(total),
        production_cost=production_cost,
        due_date=due_date,
        assigned_to=assigned_to,
        notes=notes or "",
        created_by=actor,
    )
    _save_detail(order, detail, items)
    _event(order, "", order.status, actor, "Order created")
    record_event(
        organization=organization,
        action="order.created",
        entity=order,
        actor=actor,
        request=request,
        summary={
            "number": order.number,
            "kind": kind,
            "total": str(total),
            "currency": currency,
            "customer": customer.name,
            "due_date": due_date.isoformat(),
        },
    )
    if deposit and _money(deposit["amount"]) > 0:
        pay_order(
            order,
            amount=deposit["amount"],
            method=deposit["method"],
            reference=deposit.get("reference", ""),
            amount_tendered=deposit.get("amount_tendered"),
            actor=actor,
            request=request,
        )
    return order


@transaction.atomic
def update_order(order, *, membership, actor, data, request=None):
    """Edit specifications and workflow fields of an open order. Price changes need orders.manage."""
    order = CustomOrder.objects.select_for_update().get(pk=order.pk)
    if not order.is_open:
        raise Conflict(f"{order.number} is {order.status_label.lower()} and can no longer be edited.")
    changes = {}
    if "total" in data and _money(data["total"]) != order.total:
        if not has_permission(membership, "orders.manage"):
            raise PermissionDenied("Only a manager can change an order's price.")
        total = _money(data["total"])
        if total < order.paid_amount:
            raise ValidationError({"total": [f"{order.currency} {order.paid_amount} has already been paid; the price cannot be lower."]})
        changes["total"] = (str(order.total), str(total))
        order.total = total
        order.base_total = FxSnapshot(order.currency, order.fx_units_per_usd, order.fx_rate_date).to_base(total)
    for field in ("title", "due_date", "assigned_to", "production_cost", "notes", "customer"):
        if field in data and data[field] != getattr(order, field):
            if field == "customer" and order.paid_amount > 0:
                raise ValidationError({"customer": ["This order has payments; the customer cannot be changed."]})
            changes[field] = (str(getattr(order, field)), str(data[field]))
            setattr(order, field, data[field])
    order.save()
    if "detail" in data or "items" in data:
        _save_detail(order, data.get("detail", {}), data.get("items"))
        changes["specification"] = "updated"
    if changes:
        record_event(
            organization=order.organization,
            action="order.updated",
            entity=order,
            actor=actor,
            request=request,
            summary={"number": order.number, "changes": changes},
        )
    return order


@transaction.atomic
def change_status(order, *, membership, actor, to_status, note="", request=None):
    order = CustomOrder.objects.select_for_update().get(pk=order.pk)
    flow = order.flow
    if to_status not in flow:
        raise ValidationError({"status": [f"Choose one of: {', '.join(STATUS_LABELS[s] for s in flow)}."]})
    if order.status == "cancelled":
        raise Conflict(f"{order.number} is cancelled.")
    if to_status == order.status:
        raise ValidationError({"status": [f"The order is already {order.status_label.lower()}."]})
    backwards = flow.index(to_status) < flow.index(order.status)
    if backwards:
        if not has_permission(membership, "orders.manage"):
            raise PermissionDenied("Only a manager can move an order back to an earlier step.")
        if not note.strip():
            raise ValidationError({"note": ["Explain why the status is being corrected."]})
    from_status = order.status
    order.status = to_status
    order.delivered_at = timezone.now() if to_status == "delivered" else None
    order.save(update_fields=["status", "delivered_at", "updated_at"])
    _event(order, from_status, to_status, actor, note, correction=backwards)
    record_event(
        organization=order.organization,
        action="order.status_corrected" if backwards else "order.status_changed",
        entity=order,
        actor=actor,
        request=request,
        summary={"number": order.number, "from": from_status, "to": to_status, "note": note.strip()},
    )
    return order


@transaction.atomic
def cancel_order(order, *, actor, reason, request=None):
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why the order is being cancelled."]})
    order = CustomOrder.objects.select_for_update().get(pk=order.pk)
    if order.status in CLOSED_STATUSES:
        raise Conflict(f"{order.number} is already {order.status_label.lower()}.")
    if order.paid_amount > 0:
        raise Conflict(
            f"{order.currency} {order.paid_amount} has been paid on {order.number}. Reverse or refund those payments before cancelling."
        )
    if order.materials.filter(reversed_at__isnull=True).exists():
        raise Conflict("Materials are still recorded against this order. Return them to stock before cancelling.")
    from_status = order.status
    order.status = "cancelled"
    order.cancelled_at = timezone.now()
    order.cancelled_by = actor
    order.cancel_reason = reason.strip()[:240]
    order.save(update_fields=["status", "cancelled_at", "cancelled_by", "cancel_reason", "updated_at"])
    _event(order, from_status, "cancelled", actor, order.cancel_reason)
    record_event(
        organization=order.organization,
        action="order.cancelled",
        entity=order,
        actor=actor,
        request=request,
        summary={"number": order.number, "reason": order.cancel_reason},
    )
    return order


@transaction.atomic
def use_material(order, *, actor, variant, quantity, note="", request=None):
    """Take stock out for an order (explicit, REQ-025). Valued at the current average cost."""
    if not order.is_open:
        raise Conflict(f"{order.number} is {order.status_label.lower()}; materials cannot be added.")
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError({"quantity": ["Enter a quantity greater than zero."]})
    movement = apply_movement(
        organization=order.organization,
        variant=variant,
        branch=order.branch,
        quantity_delta=-quantity,
        movement_type=StockMovement.Type.ORDER_CONSUMPTION,
        actor=actor,
        source=order,
        reason=f"Used for {order.number}",
    )
    material = OrderMaterial.objects.create(
        order=order,
        variant=variant,
        branch=order.branch,
        quantity=quantity,
        unit_cost_base=movement.unit_cost_base,
        movement=movement,
        note=(note or "")[:240],
        created_by=actor,
    )
    record_event(
        organization=order.organization,
        action="order.material_used",
        entity=order,
        actor=actor,
        request=request,
        summary={"number": order.number, "variant": str(variant), "quantity": str(quantity)},
    )
    return material


@transaction.atomic
def return_material(material, *, actor, reason, request=None):
    """Put unused material back into stock at the cost it left with."""
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why the material is being returned."]})
    material = OrderMaterial.objects.select_for_update().select_related("order").get(pk=material.pk)
    if material.reversed_at:
        raise Conflict("This material has already been returned to stock.")
    movement = apply_movement(
        organization=material.order.organization,
        variant=material.variant,
        branch=material.branch,
        quantity_delta=material.quantity,
        movement_type=StockMovement.Type.ORDER_RETURN,
        actor=actor,
        unit_cost_base=material.unit_cost_base,
        source=material.order,
        reason=f"Returned from {material.order.number}: {reason.strip()}"[:240],
    )
    material.reversal_movement = movement
    material.reversed_at = timezone.now()
    material.reversed_by = actor
    material.reversal_reason = reason.strip()[:240]
    material.save(update_fields=["reversal_movement", "reversed_at", "reversed_by", "reversal_reason"])
    record_event(
        organization=material.order.organization,
        action="order.material_returned",
        entity=material.order,
        actor=actor,
        request=request,
        summary={"number": material.order.number, "quantity": str(material.quantity), "reason": material.reversal_reason},
    )
    return material
