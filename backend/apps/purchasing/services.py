"""Purchase and goods-receiving services.

Stock increases only when goods are received (REQ-016), through
apps.inventory.services.apply_movement, in the same transaction as the receipt.

Landed cost (provisional policy, pending accountant approval): shipping and
other costs are spread across lines in proportion to line value, and become
part of each unit's cost.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_event
from apps.common.exceptions import Conflict
from apps.common.numbering import next_number
from apps.currencies.services import FxSnapshot, snapshot_for
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement
from apps.purchasing.models import GoodsReceipt, GoodsReceiptLine, Purchase, PurchaseLine

CENTS = Decimal("0.01")
COST_PLACES = Decimal("0.0001")
EDITABLE = (Purchase.Status.OPEN,)


def _money(value):
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def _validate_lines(purchase_section, lines):
    if not lines:
        raise ValidationError({"lines": ["Add at least one item."]})
    seen = set()
    for index, line in enumerate(lines):
        variant = line["variant"]
        if variant.product.section_id != purchase_section.pk:
            raise ValidationError({f"lines.{index}.variant": ["Choose an item from the purchase's section."]})
        if variant.pk in seen:
            raise ValidationError({f"lines.{index}.variant": ["This item is already on the purchase; change its quantity instead."]})
        seen.add(variant.pk)
        if line["quantity"] <= 0:
            raise ValidationError({f"lines.{index}.quantity": ["Quantity must be greater than zero."]})
        if line["unit_cost"] < 0:
            raise ValidationError({f"lines.{index}.unit_cost": ["Cost cannot be negative."]})


def _write_lines_and_totals(purchase, lines):
    purchase.lines.all().delete()
    subtotal = Decimal("0")
    for position, line in enumerate(lines):
        variant = line["variant"]
        line_total = _money(line["quantity"] * line["unit_cost"])
        subtotal += line_total
        PurchaseLine.objects.create(
            purchase=purchase,
            variant=variant,
            position=position,
            description=line.get("description") or str(variant),
            quantity=line["quantity"],
            unit_cost=line["unit_cost"],
            line_total=line_total,
        )
    purchase.subtotal = subtotal
    purchase.total = subtotal + purchase.shipping_cost + purchase.other_cost
    fx = snapshot_from(purchase)
    purchase.base_total = fx.to_base(purchase.total)


def snapshot_from(purchase):
    return FxSnapshot(purchase.currency, purchase.fx_units_per_usd, purchase.fx_rate_date)


@transaction.atomic
def create_purchase(
    *,
    organization,
    actor,
    supplier,
    section,
    branch,
    purchase_date,
    currency,
    lines,
    shipping_cost=Decimal("0"),
    other_cost=Decimal("0"),
    supplier_reference="",
    notes="",
    request=None,
):
    _validate_lines(section, lines)
    fx = snapshot_for(organization, currency, purchase_date)
    purchase = Purchase.objects.create(
        organization=organization,
        number=next_number(organization, "PO"),
        supplier=supplier,
        section=section,
        branch=branch,
        purchase_date=purchase_date,
        currency=currency,
        fx_units_per_usd=fx.units_per_usd,
        fx_rate_to_base=fx.rate_to_base,
        fx_rate_date=fx.rate_date,
        shipping_cost=shipping_cost,
        other_cost=other_cost,
        supplier_reference=supplier_reference,
        notes=notes,
        created_by=actor,
    )
    _write_lines_and_totals(purchase, lines)
    purchase.save()
    record_event(
        organization=organization,
        action="purchase.created",
        entity=purchase,
        actor=actor,
        request=request,
        summary={
            "number": purchase.number,
            "supplier": str(supplier.pk),
            "currency": currency,
            "total": str(purchase.total),
            "base_total": str(purchase.base_total),
            "lines": len(lines),
        },
    )
    return purchase


@transaction.atomic
def update_purchase(purchase, *, actor, request=None, lines=None, **fields):
    """Edit an open purchase that has nothing received. Re-snapshots FX if currency/date changes."""
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status not in EDITABLE or purchase.lines.filter(quantity_received__gt=0).exists():
        raise Conflict("Only open purchases with nothing received can be edited.")
    for name, value in fields.items():
        setattr(purchase, name, value)
    if "currency" in fields or "purchase_date" in fields:
        fx = snapshot_for(purchase.organization, purchase.currency, purchase.purchase_date)
        purchase.fx_units_per_usd, purchase.fx_rate_to_base, purchase.fx_rate_date = fx.units_per_usd, fx.rate_to_base, fx.rate_date
    if lines is not None:
        _validate_lines(purchase.section, lines)
        _write_lines_and_totals(purchase, lines)
    else:
        purchase.total = purchase.subtotal + purchase.shipping_cost + purchase.other_cost
        purchase.base_total = snapshot_from(purchase).to_base(purchase.total)
    if purchase.total < purchase.paid_amount:
        raise ValidationError({"lines": [f"The new total ({purchase.total}) would be less than the {purchase.paid_amount} already paid."]})
    purchase.save()
    record_event(
        organization=purchase.organization,
        action="purchase.updated",
        entity=purchase,
        actor=actor,
        request=request,
        summary={"fields": sorted(fields) + (["lines"] if lines is not None else []), "total": str(purchase.total)},
    )
    return purchase


def landed_unit_costs(purchase):
    """{line_id: landed unit cost in transaction currency}. Extra costs split by line value."""
    lines = list(purchase.lines.all())
    extra = purchase.shipping_cost + purchase.other_cost
    goods_value = sum((line.line_total for line in lines), Decimal("0"))
    result = {}
    for line in lines:
        share = (extra * line.line_total / goods_value) if goods_value > 0 else (extra / len(lines))
        result[line.pk] = (line.unit_cost + share / line.quantity).quantize(COST_PLACES, rounding=ROUND_HALF_UP)
    return result


def _refresh_status(purchase):
    lines = list(purchase.lines.all())
    received = [line.quantity_received for line in lines]
    if all(r == 0 for r in received):
        purchase.status = Purchase.Status.OPEN
    elif all(line.quantity_received >= line.quantity for line in lines):
        purchase.status = Purchase.Status.RECEIVED
    else:
        purchase.status = Purchase.Status.PARTIAL
    purchase.save(update_fields=["status", "updated_at"])


@transaction.atomic
def receive_goods(purchase, *, actor, quantities, received_date=None, note="", request=None):
    """Receive {purchase_line_id: quantity}. Adds stock once per receipt; never beyond what was ordered."""
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status in (Purchase.Status.CANCELLED, Purchase.Status.RECEIVED):
        raise Conflict(f"This purchase is {purchase.get_status_display().lower()}; nothing more can be received.")
    lines = {str(line.pk): line for line in purchase.lines.select_for_update().select_related("variant__product")}
    wanted = {key: Decimal(value) for key, value in quantities.items() if Decimal(value) != 0}
    if not wanted:
        raise ValidationError({"lines": ["Enter a quantity for at least one item."]})
    for key, qty in wanted.items():
        line = lines.get(key)
        if line is None:
            raise ValidationError({f"lines.{key}": ["This item is not on the purchase."]})
        if qty < 0:
            raise ValidationError({f"lines.{key}": ["Quantity must be greater than zero."]})
        if qty > line.quantity_outstanding:
            raise ValidationError({f"lines.{key}": [f"Only {line.quantity_outstanding.normalize():f} still to receive."]})

    fx = snapshot_from(purchase)
    landed = landed_unit_costs(purchase)
    receipt = GoodsReceipt.objects.create(
        organization=purchase.organization,
        purchase=purchase,
        number=next_number(purchase.organization, "GRN"),
        received_date=received_date or timezone.localdate(),
        note=note,
        created_by=actor,
    )
    for key, qty in wanted.items():
        line = lines[key]
        unit_base = fx.to_base(landed[line.pk], COST_PLACES)
        movement = None
        if line.variant.product.tracks_stock:
            movement = apply_movement(
                organization=purchase.organization,
                variant=line.variant,
                branch=purchase.branch,
                quantity_delta=qty,
                movement_type=StockMovement.Type.RECEIPT,
                actor=actor,
                unit_cost_base=unit_base,
                source=receipt,
                reason=f"{purchase.number} · {purchase.supplier.name}",
            )
        GoodsReceiptLine.objects.create(
            receipt=receipt,
            purchase_line=line,
            quantity=qty,
            landed_unit_cost=landed[line.pk],
            landed_unit_cost_base=unit_base,
            movement=movement,
        )
        line.quantity_received += qty
        line.save(update_fields=["quantity_received"])
    _refresh_status(purchase)
    record_event(
        organization=purchase.organization,
        action="purchase.received",
        entity=receipt,
        actor=actor,
        request=request,
        summary={"purchase": purchase.number, "receipt": receipt.number, "lines": {key: str(qty) for key, qty in wanted.items()}},
    )
    return receipt


@transaction.atomic
def reverse_receipt(receipt, *, actor, reason, request=None):
    """Undo a delivery recorded in error. Fails if the stock has already been used."""
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why this receipt is being reversed."]})
    receipt = GoodsReceipt.objects.select_for_update().get(pk=receipt.pk)
    if receipt.reversed_at:
        raise Conflict("This receipt has already been reversed.")
    purchase = Purchase.objects.select_for_update().get(pk=receipt.purchase_id)
    for receipt_line in receipt.lines.select_related("purchase_line__variant__product"):
        line = receipt_line.purchase_line
        if receipt_line.movement_id:
            receipt_line.reversal_movement = apply_movement(
                organization=purchase.organization,
                variant=line.variant,
                branch=purchase.branch,
                quantity_delta=-receipt_line.quantity,
                movement_type=StockMovement.Type.RECEIPT_REVERSAL,
                actor=actor,
                source=receipt,
                unit_cost_base=receipt_line.landed_unit_cost_base,
                outbound_at_cost=True,
                reason=f"Reversal of {receipt.number}: {reason}"[:240],
            )
            receipt_line.save(update_fields=["reversal_movement"])
        line.quantity_received -= receipt_line.quantity
        line.save(update_fields=["quantity_received"])
    receipt.reversed_at = timezone.now()
    receipt.reversed_by = actor
    receipt.reversal_reason = reason.strip()
    receipt.save(update_fields=["reversed_at", "reversed_by", "reversal_reason"])
    _refresh_status(purchase)
    record_event(
        organization=purchase.organization,
        action="purchase.receipt_reversed",
        entity=receipt,
        actor=actor,
        request=request,
        summary={"purchase": purchase.number, "receipt": receipt.number, "reason": reason.strip()},
    )
    return receipt


@transaction.atomic
def cancel_purchase(purchase, *, actor, reason, request=None):
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why this purchase is being cancelled."]})
    purchase = Purchase.objects.select_for_update().get(pk=purchase.pk)
    if purchase.status == Purchase.Status.CANCELLED:
        raise Conflict("This purchase is already cancelled.")
    if purchase.lines.filter(quantity_received__gt=0).exists():
        raise Conflict("Reverse its goods receipts before cancelling a purchase that has stock received.")
    if purchase.paid_amount > 0:
        raise Conflict("Reverse the supplier payments on this purchase before cancelling it.")
    purchase.status = Purchase.Status.CANCELLED
    purchase.cancelled_by = actor
    purchase.cancel_reason = reason.strip()
    purchase.save(update_fields=["status", "cancelled_by", "cancel_reason", "updated_at"])
    record_event(
        organization=purchase.organization,
        action="purchase.cancelled",
        entity=purchase,
        actor=actor,
        request=request,
        summary={"number": purchase.number, "reason": purchase.cancel_reason},
    )
    return purchase
