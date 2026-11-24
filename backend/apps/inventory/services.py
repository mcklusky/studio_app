"""Stock domain services. The only code allowed to change StockBalance.

Valuation basis: moving weighted-average cost in the organization's base
currency (provisional; owner/accountant approval pending, see prd.md).
"""

from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_event
from apps.catalog.models import ProductVariant
from apps.inventory.models import StockAdjustment, StockBalance, StockMovement

COST_PLACES = Decimal("0.0001")
QTY_PLACES = Decimal("0.001")
VALUATION_BASIS = "moving_weighted_average"


class InsufficientStock(ValidationError):
    default_code = "insufficient_stock"


def ensure_default_variant(product):
    """Stock is always held against a variant; products without options get 'default'."""
    variant, _ = ProductVariant.objects.get_or_create(product=product, code="default")
    return variant


def _lock_balance(organization, variant, branch):
    balance, _ = StockBalance.objects.select_for_update().get_or_create(
        variant=variant,
        branch=branch,
        defaults={"organization": organization},
    )
    return balance


def apply_movement(
    *,
    organization,
    variant,
    branch,
    quantity_delta,
    movement_type,
    actor,
    unit_cost_base=None,
    source=None,
    reason="",
    outbound_at_cost=False,
):
    """Lock the balance, validate, append a movement, and update the balance. Atomic.

    Inbound movements with a unit cost re-average the cost; inbound without a
    cost (e.g. a return) and ordinary outbound movements use the current average.
    With outbound_at_cost=True (reversing a receipt), units leave at the given
    cost so the average returns to what it was before that receipt.
    """
    quantity_delta = Decimal(quantity_delta).quantize(QTY_PLACES)
    if quantity_delta == 0:
        raise ValidationError({"quantity_delta": ["Quantity change cannot be zero."]})
    if variant.product.organization_id != organization.pk or branch.organization_id != organization.pk:
        raise ValidationError("Product and branch must belong to this organization.")
    if not variant.product.tracks_stock:
        raise ValidationError({"variant": ["This product does not track stock."]})

    with transaction.atomic():
        balance = _lock_balance(organization, variant, branch)
        new_quantity = balance.quantity + quantity_delta
        if new_quantity < 0:
            raise InsufficientStock(
                {"quantity_delta": [f"Only {balance.quantity.normalize():f} in stock; cannot remove {(-quantity_delta).normalize():f}."]}
            )

        priced = unit_cost_base is not None and (quantity_delta > 0 or outbound_at_cost)
        if priced:
            unit_cost = Decimal(unit_cost_base).quantize(COST_PLACES, rounding=ROUND_HALF_UP)
            if unit_cost < 0:
                raise ValidationError({"unit_cost_base": ["Cost cannot be negative."]})
            if new_quantity > 0:
                total_value = balance.quantity * balance.average_cost_base + quantity_delta * unit_cost
                new_average = max(Decimal("0"), total_value / new_quantity).quantize(COST_PLACES, rounding=ROUND_HALF_UP)
            else:
                new_average = balance.average_cost_base
        else:
            unit_cost = balance.average_cost_base
            new_average = balance.average_cost_base

        movement = StockMovement.objects.create(
            organization=organization,
            variant=variant,
            branch=branch,
            movement_type=movement_type,
            quantity_delta=quantity_delta,
            unit_cost_base=unit_cost,
            quantity_after=new_quantity,
            average_cost_after=new_average,
            reason=reason,
            created_by=actor,
            source_type=source._meta.label_lower if source is not None else "",
            source_id=str(source.pk) if source is not None else "",
        )
        balance.quantity = new_quantity
        balance.average_cost_base = new_average
        balance.save(update_fields=["quantity", "average_cost_base", "updated_at"])
        return movement


def adjust_stock(*, organization, variant, branch, quantity_delta, reason, actor, note="", unit_cost_base=None, request=None):
    """Record a reasoned manual adjustment with its movement and audit event."""
    if reason not in StockAdjustment.Reason.values:
        raise ValidationError({"reason": ["Choose a reason for this adjustment."]})
    if reason in (StockAdjustment.Reason.OTHER, StockAdjustment.Reason.COUNT) and not note.strip():
        raise ValidationError({"note": ["Explain this adjustment."]})
    if reason == StockAdjustment.Reason.OPENING and (unit_cost_base is None or Decimal(quantity_delta) <= 0):
        raise ValidationError({"unit_cost_base": ["Opening stock needs a positive quantity and a unit cost."]})
    if reason in (StockAdjustment.Reason.DAMAGE, StockAdjustment.Reason.LOSS) and Decimal(quantity_delta) > 0:
        raise ValidationError({"quantity_delta": ["Damage and loss must reduce stock."]})

    movement_type = StockMovement.Type.OPENING if reason == StockAdjustment.Reason.OPENING else StockMovement.Type.ADJUSTMENT
    label = StockAdjustment.Reason(reason).label
    with transaction.atomic():
        movement = apply_movement(
            organization=organization,
            variant=variant,
            branch=branch,
            quantity_delta=quantity_delta,
            movement_type=movement_type,
            actor=actor,
            unit_cost_base=unit_cost_base,
            reason=f"{label}: {note}" if note else label,
        )
        adjustment = StockAdjustment.objects.create(
            organization=organization,
            variant=variant,
            branch=branch,
            reason=reason,
            note=note,
            quantity_delta=movement.quantity_delta,
            unit_cost_base=unit_cost_base,
            movement=movement,
            created_by=actor,
        )
        record_event(
            organization=organization,
            action="stock.adjusted",
            entity=adjustment,
            actor=actor,
            request=request,
            summary={
                "variant": str(variant.pk),
                "branch": str(branch.pk),
                "reason": reason,
                "quantity_delta": str(movement.quantity_delta),
                "quantity_after": str(movement.quantity_after),
            },
        )
        return adjustment


def reconcile(variant, branch):
    """Return (balance_quantity, ledger_sum). They must always match."""
    ledger = StockMovement.objects.filter(variant=variant, branch=branch).aggregate(total=Sum("quantity_delta"))["total"] or Decimal("0")
    balance = StockBalance.objects.filter(variant=variant, branch=branch).values_list("quantity", flat=True).first() or Decimal("0")
    return balance, ledger


def stock_status(quantity, minimum):
    if quantity <= 0:
        return "out"
    if minimum and quantity <= minimum:
        return "low"
    return "ok"
