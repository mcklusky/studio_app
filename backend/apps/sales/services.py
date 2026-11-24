"""Sale pricing, posting and reversal.

The server is the source of truth for every amount: client prices are inputs
to validate, not totals to trust. Posting commits the sale, its stock
movements, any initial payment and the audit event in one transaction.
"""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.audit.services import record_event
from apps.common.exceptions import Conflict
from apps.common.numbering import next_number
from apps.currencies.services import FxSnapshot, snapshot_for
from apps.identity.scope import has_permission
from apps.inventory.models import StockBalance, StockMovement
from apps.inventory.services import InsufficientStock, apply_movement
from apps.payments.services import pay_sale, reverse_payments_for_sale, validate_payment_input
from apps.sales.models import Sale, SaleLine

CENTS = Decimal("0.01")
ZERO = Decimal("0")


def money(value):
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


@dataclass
class PricedLine:
    product: object
    variant: object
    description: str
    quantity: Decimal
    list_price: Decimal
    unit_price: Decimal
    discount: Decimal
    price_overridden: bool
    available: Decimal | None = None

    @property
    def gross(self):
        return money(self.quantity * self.unit_price)

    @property
    def line_total(self):
        return self.gross - self.discount


@dataclass
class PricedSale:
    fx: FxSnapshot
    lines: list = field(default_factory=list)
    sale_discount: Decimal = ZERO

    @property
    def subtotal(self):
        return sum((line.gross for line in self.lines), ZERO)

    @property
    def line_discount_total(self):
        return sum((line.discount for line in self.lines), ZERO)

    @property
    def total(self):
        return self.subtotal - self.line_discount_total - self.sale_discount

    @property
    def stock_problems(self):
        return {index: line for index, line in enumerate(self.lines) if line.available is not None and line.available < 0}


def describe(product, variant):
    if variant is None or variant.code == "default":
        return product.name
    options = " / ".join(part for part in (variant.size, variant.color) if part)
    return f"{product.name} · {options or variant.code}"


def _resolve_variant(index, product, variant):
    if variant is not None:
        if variant.product_id != product.pk or not variant.active:
            raise ValidationError({f"items.{index}.variant": ["Choose an available size/colour of this product."]})
        return variant
    if not product.tracks_stock:
        return None
    options = [v for v in product.variants.all() if v.active]
    if len(options) == 1:
        return options[0]
    raise ValidationError({f"items.{index}.variant": [f"Choose a size/colour for {product.name}."]})


def price_sale(*, membership, section, branch, currency, items, sale_discount=ZERO, on_date=None):
    """Validate and price a sale without saving anything. Used by preview and post."""
    organization = membership.organization
    fx = snapshot_for(organization, currency, on_date or timezone.localdate())
    can_override = has_permission(membership, "sales.price_override")
    if not items:
        raise ValidationError({"items": ["Add at least one item."]})

    priced = PricedSale(fx=fx, sale_discount=money(sale_discount or ZERO))
    for index, item in enumerate(items):
        product = item["product"]
        if product.organization_id != organization.pk or product.section_id != section.pk:
            raise ValidationError({f"items.{index}.product": ["Choose a product from this sale's section."]})
        if product.status != product.Status.ACTIVE:
            raise ValidationError({f"items.{index}.product": [f"{product.name} is inactive and cannot be sold."]})
        variant = _resolve_variant(index, product, item.get("variant"))
        quantity = Decimal(item["quantity"])
        if quantity <= 0:
            raise ValidationError({f"items.{index}.quantity": ["Quantity must be greater than zero."]})
        list_price = money(product.selling_price_base * fx.units_per_usd)
        unit_price = list_price if item.get("unit_price") is None else money(item["unit_price"])
        overridden = unit_price != list_price
        if unit_price < 0:
            raise ValidationError({f"items.{index}.unit_price": ["Price cannot be negative."]})
        if overridden and not can_override:
            raise ValidationError(
                {
                    f"items.{index}.unit_price": [
                        f"Price must be {currency} {list_price}. Ask a manager to change prices, or give a discount."
                    ]
                }
            )
        line = PricedLine(
            product=product,
            variant=variant,
            description=describe(product, variant),
            quantity=quantity,
            list_price=list_price,
            unit_price=unit_price,
            discount=money(item.get("discount") or ZERO),
            price_overridden=overridden,
        )
        if line.discount < 0 or line.discount > line.gross:
            raise ValidationError({f"items.{index}.discount": [f"Discount must be between 0 and {currency} {line.gross}."]})
        priced.lines.append(line)

    after_line_discounts = priced.subtotal - priced.line_discount_total
    if priced.sale_discount < 0 or priced.sale_discount > after_line_discounts:
        raise ValidationError({"sale_discount": [f"Discount must be between 0 and {currency} {after_line_discounts}."]})

    # Availability (informational for preview; posting re-checks under row locks).
    needed = {}
    for line in priced.lines:
        if line.variant is not None and line.product.tracks_stock:
            needed[line.variant.pk] = needed.get(line.variant.pk, ZERO) + line.quantity
            on_hand = StockBalance.objects.filter(variant=line.variant, branch=branch).aggregate(q=Sum("quantity"))["q"] or ZERO
            line.available = on_hand - needed[line.variant.pk]
    return priced


@transaction.atomic
def post_sale(
    *, membership, actor, section, branch, currency, items, customer=None, sale_discount=ZERO, payment=None, notes="", request=None
):
    organization = membership.organization
    priced = price_sale(membership=membership, section=section, branch=branch, currency=currency, items=items, sale_discount=sale_discount)
    paying = ZERO
    if payment:
        paying, _ = validate_payment_input(payment["amount"], payment["method"], payment.get("amount_tendered"))
        if paying > priced.total:
            raise ValidationError({"payment.amount": [f"Payment cannot exceed the sale total of {currency} {priced.total}."]})
    if customer is None and paying < priced.total:
        raise ValidationError({"customer": ["Choose a customer: a sale with a balance due needs someone to collect from."]})

    sale = Sale.objects.create(
        organization=organization,
        number=next_number(organization, "INV"),
        section=section,
        branch=branch,
        customer=customer,
        currency=currency,
        fx_units_per_usd=priced.fx.units_per_usd,
        fx_rate_to_base=priced.fx.rate_to_base,
        fx_rate_date=priced.fx.rate_date,
        subtotal=priced.subtotal,
        line_discount_total=priced.line_discount_total,
        sale_discount=priced.sale_discount,
        total=priced.total,
        base_total=priced.fx.to_base(priced.total),
        notes=notes[:500],
        created_by=actor,
    )
    cost_total = ZERO
    for position, line in enumerate(priced.lines):
        movement = None
        if line.variant is not None and line.product.tracks_stock:
            try:
                movement = apply_movement(
                    organization=organization,
                    variant=line.variant,
                    branch=branch,
                    quantity_delta=-line.quantity,
                    movement_type=StockMovement.Type.SALE,
                    actor=actor,
                    source=sale,
                    reason=f"Sale {sale.number}",
                )
            except InsufficientStock as exc:
                raise InsufficientStock({f"items.{position}.quantity": exc.detail["quantity_delta"]}) from exc
            cost_total += movement.unit_cost_base * line.quantity
        SaleLine.objects.create(
            sale=sale,
            product=line.product,
            variant=line.variant,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            discount=line.discount,
            line_total=line.line_total,
            price_overridden=line.price_overridden,
            unit_cost_base=movement.unit_cost_base if movement else None,
            movement=movement,
            position=position,
        )
    sale.cost_total_base = cost_total
    sale.save(update_fields=["cost_total_base"])
    if paying > 0:
        pay_sale(
            sale,
            amount=paying,
            method=payment["method"],
            reference=payment.get("reference") or "",
            amount_tendered=payment.get("amount_tendered"),
            actor=actor,
            request=request,
        )
    record_event(
        organization=organization,
        action="sale.posted",
        entity=sale,
        actor=actor,
        request=request,
        summary={
            "number": sale.number,
            "currency": currency,
            "total": str(sale.total),
            "paid": str(paying),
            "lines": len(priced.lines),
            "price_overrides": sum(1 for line in priced.lines if line.price_overridden),
        },
    )
    return sale


@transaction.atomic
def reverse_sale(sale, *, actor, reason, request=None):
    """Void a posted sale: return stock at its original cost and reverse its payments (refund)."""
    if not reason.strip():
        raise ValidationError({"reason": ["Explain why this sale is being reversed."]})
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status != Sale.Status.POSTED:
        raise Conflict("This sale has already been reversed.")
    for line in sale.lines.select_related("variant__product").filter(movement__isnull=False):
        line.reversal_movement = apply_movement(
            organization=sale.organization,
            variant=line.variant,
            branch=sale.branch,
            quantity_delta=line.quantity,
            movement_type=StockMovement.Type.SALE_REVERSAL,
            actor=actor,
            source=sale,
            unit_cost_base=line.unit_cost_base,
            reason=f"Reversal of {sale.number}: {reason}"[:240],
        )
        line.save(update_fields=["reversal_movement"])
    reverse_payments_for_sale(sale, actor=actor, reason=reason)
    sale.status = Sale.Status.REVERSED
    sale.reversed_at = timezone.now()
    sale.reversed_by = actor
    sale.reversal_reason = reason.strip()[:240]
    sale.save(update_fields=["status", "reversed_at", "reversed_by", "reversal_reason"])
    record_event(
        organization=sale.organization,
        action="sale.reversed",
        entity=sale,
        actor=actor,
        request=request,
        summary={"number": sale.number, "reason": sale.reversal_reason, "refunded": str(sale.paid_amount)},
    )
    return sale
