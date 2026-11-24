"""Dashboard and report figures. One set of definitions, shared by every screen.

All consolidated figures are in the USD reporting base, converted with each
transaction's own saved FX snapshot (never today's rate). Original-currency
subtotals are reported beside them and never added together.

Definitions (prd.md §8; provisional until the accountant signs off):
* Sales: posted sales by posting date. Reversed sales are excluded.
* Orders delivered: department orders by delivery date, at their agreed price.
  (Provisional: orders count as revenue when delivered; deposits before then are
  cash collected, not sales.)
* Cash collected: posted customer payments by date received, per allocation, so a
  section filter counts only the part of a payment applied to that section.
* Purchases: supplier purchases by purchase date, excluding cancelled ones. Not an
  expense: inventory cost reaches profit when goods are sold (COGS).
* Cost of goods sold: weighted-average cost of tracked items sold, plus stock
  materials used on delivered orders.
* Gross profit = sales + orders delivered − cost of goods sold.
* Net profit = gross profit − expenses (posted, by expense date).
* Balances and stock value are "as of now", not for the period.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.expenses.models import Expense
from apps.identity.scope import allowed_branch_ids, allowed_section_ids
from apps.inventory.models import StockBalance
from apps.orders.models import CLOSED_STATUSES, CustomOrder, OrderMaterial
from apps.payments.models import CustomerPaymentAllocation
from apps.purchasing.models import Purchase
from apps.sales.models import Sale, SaleLine

CENTS = Decimal("0.01")
ZERO = Decimal("0")
MAX_PERIOD_DAYS = 366 * 3
BIG = DecimalField(max_digits=24, decimal_places=8)


def money(value):
    return (value or ZERO).quantize(CENTS, rounding=ROUND_HALF_UP)


def s(value):
    return str(money(value))


@dataclass(frozen=True)
class ReportScope:
    organization_id: object
    start: date
    end: date
    section_ids: tuple
    branch_ids: tuple

    @property
    def days(self):
        return (self.end - self.start).days + 1

    def previous(self):
        """The period of the same length just before this one (for comparisons)."""
        end = self.start - timedelta(days=1)
        return ReportScope(self.organization_id, end - timedelta(days=self.days - 1), end, self.section_ids, self.branch_ids)

    def scoped(self, queryset, section="section_id", branch="branch_id"):
        return queryset.filter(
            **{"organization_id": self.organization_id, f"{section}__in": self.section_ids, f"{branch}__in": self.branch_ids}
        )


def build_scope(membership, *, start=None, end=None, section=None, branch=None):
    """Resolve filters against the user's permitted sections/branches. Unknown ids are refused."""
    from rest_framework.exceptions import ValidationError

    today = timezone.localdate()
    start, end = start or today, end or today
    if end < start:
        raise ValidationError({"to": ["The end date is before the start date."]})
    if (end - start).days > MAX_PERIOD_DAYS:
        raise ValidationError({"from": ["Choose a period of three years or less."]})
    sections, branches = allowed_section_ids(membership), allowed_branch_ids(membership)
    if section:
        sections = [s_id for s_id in sections if str(s_id) == str(section)]
        if not sections:
            raise ValidationError({"section": ["Choose a section you have access to."]})
    if branch:
        branches = [b_id for b_id in branches if str(b_id) == str(branch)]
        if not branches:
            raise ValidationError({"branch": ["Choose a branch you have access to."]})
    return ReportScope(membership.organization_id, start, end, tuple(sections), tuple(branches))


# ---------- querysets ----------


def sales_in(scope):
    return scope.scoped(Sale.objects.filter(status=Sale.Status.POSTED, posted_at__date__gte=scope.start, posted_at__date__lte=scope.end))


def delivered_orders_in(scope):
    return scope.scoped(
        CustomOrder.objects.filter(status="delivered", delivered_at__date__gte=scope.start, delivered_at__date__lte=scope.end)
    )


def allocations_in(scope):
    """Posted customer payment allocations received in the period, in scope via their sale or order."""
    sale_scope = Q(sale__section_id__in=scope.section_ids, sale__branch_id__in=scope.branch_ids)
    order_scope = Q(custom_order__section_id__in=scope.section_ids, custom_order__branch_id__in=scope.branch_ids)
    return CustomerPaymentAllocation.objects.filter(
        sale_scope | order_scope,
        payment__organization_id=scope.organization_id,
        payment__status="posted",
        payment__received_at__date__gte=scope.start,
        payment__received_at__date__lte=scope.end,
    )


def purchases_in(scope):
    return scope.scoped(
        Purchase.objects.exclude(status=Purchase.Status.CANCELLED).filter(purchase_date__gte=scope.start, purchase_date__lte=scope.end)
    )


def expenses_in(scope):
    return scope.scoped(Expense.objects.filter(status=Expense.Status.POSTED, expense_date__gte=scope.start, expense_date__lte=scope.end))


ALLOCATION_BASE = ExpressionWrapper(F("amount") / F("payment__fx_units_per_usd"), output_field=BIG)
MATERIAL_COST = ExpressionWrapper(F("quantity") * F("unit_cost_base"), output_field=BIG)


def _sum(queryset, field):
    return queryset.aggregate(t=Coalesce(Sum(field), ZERO, output_field=BIG))["t"]


def _by_currency(queryset, field):
    return {row["currency"]: s(row["t"]) for row in queryset.values("currency").annotate(t=Sum(field)).order_by("currency") if row["t"]}


# ---------- figures ----------


def order_material_cost(orders):
    return _sum(OrderMaterial.objects.filter(order__in=orders, reversed_at__isnull=True), MATERIAL_COST)


def financials(scope):
    """The period's headline figures in USD base, plus original-currency subtotals."""
    sales = sales_in(scope)
    orders = delivered_orders_in(scope)
    allocations = allocations_in(scope)
    purchases = purchases_in(scope)
    expenses = expenses_in(scope)

    sales_base = _sum(sales, "base_total")
    orders_base = _sum(orders, "base_total")
    cogs = _sum(sales, "cost_total_base") + order_material_cost(orders)
    expenses_base = _sum(expenses, "base_amount")
    gross = sales_base + orders_base - cogs
    cash_by_currency = defaultdict(Decimal)
    for row in allocations.values("payment__currency").annotate(t=Sum("amount")):
        cash_by_currency[row["payment__currency"]] += row["t"]
    return {
        "sales": {"base": s(sales_base), "count": sales.count(), "by_currency": _by_currency(sales, "total")},
        "orders_delivered": {"base": s(orders_base), "count": orders.count(), "by_currency": _by_currency(orders, "total")},
        "revenue_base": s(sales_base + orders_base),
        "cash_collected": {
            "base": s(_sum(allocations, ALLOCATION_BASE)),
            "by_currency": {c: s(v) for c, v in sorted(cash_by_currency.items())},
        },
        "purchases": {
            "base": s(_sum(purchases, "base_total")),
            "count": purchases.count(),
            "by_currency": _by_currency(purchases, "total"),
        },
        "expenses": {"base": s(expenses_base), "count": expenses.count(), "by_currency": _by_currency(expenses, "amount")},
        "cost_of_goods_sold_base": s(cogs),
        "gross_profit_base": s(gross),
        "net_profit_base": s(gross - expenses_base),
    }


def daily_series(scope):
    """Revenue (sales + delivered orders) and cash per day, USD base."""
    revenue, cash = defaultdict(Decimal), defaultdict(Decimal)
    for row in sales_in(scope).annotate(d=TruncDate("posted_at")).values("d").annotate(t=Sum("base_total")):
        revenue[row["d"]] += row["t"]
    for row in delivered_orders_in(scope).annotate(d=TruncDate("delivered_at")).values("d").annotate(t=Sum("base_total")):
        revenue[row["d"]] += row["t"]
    for row in allocations_in(scope).annotate(d=TruncDate("payment__received_at")).values("d").annotate(t=Sum(ALLOCATION_BASE)):
        cash[row["d"]] += row["t"]
    days = []
    day = scope.start
    while day <= scope.end:
        days.append({"date": day.isoformat(), "revenue_base": s(revenue.get(day)), "cash_base": s(cash.get(day))})
        day += timedelta(days=1)
    return days


def by_section(scope):
    from apps.organizations.models import BusinessSection

    rows = {
        sec.pk: {"id": str(sec.pk), "name": sec.name, "code": sec.code, "revenue": ZERO, "expenses": ZERO}
        for sec in BusinessSection.objects.filter(pk__in=scope.section_ids)
    }
    for qs, field, key in (
        (sales_in(scope), "base_total", "revenue"),
        (delivered_orders_in(scope), "base_total", "revenue"),
        (expenses_in(scope), "base_amount", "expenses"),
    ):
        for row in qs.values("section_id").annotate(t=Sum(field)):
            rows[row["section_id"]][key] += row["t"]
    result = [
        {"id": r["id"], "name": r["name"], "code": r["code"], "revenue_base": s(r["revenue"]), "expenses_base": s(r["expenses"])}
        for r in rows.values()
    ]
    return sorted(result, key=lambda r: (-Decimal(r["revenue_base"]), r["name"]))


def _open_documents(scope):
    sales = scope.scoped(Sale.objects.filter(status=Sale.Status.POSTED, paid_amount__lt=F("total")))
    orders = scope.scoped(CustomOrder.objects.exclude(status="cancelled").filter(paid_amount__lt=F("total")))
    return sales, orders


DUE_BASE = ExpressionWrapper((F("total") - F("paid_amount")) / F("fx_units_per_usd"), output_field=BIG)


def receivables(scope, limit=None):
    """What customers owe now: per currency, a USD equivalent at each document's own rate, and top debtors."""
    sales, orders = _open_documents(scope)
    by_currency, base, customers = defaultdict(Decimal), ZERO, {}
    for qs in (sales, orders):
        for row in qs.values("customer_id", "customer__name", "currency").annotate(
            due=Sum(F("total") - F("paid_amount")), base=Sum(DUE_BASE)
        ):
            by_currency[row["currency"]] += row["due"]
            base += row["base"]
            entry = customers.setdefault(
                row["customer_id"],
                {
                    "id": str(row["customer_id"]),
                    "name": row["customer__name"] or "Walk-in",
                    "by_currency": defaultdict(Decimal),
                    "base": ZERO,
                },
            )
            entry["by_currency"][row["currency"]] += row["due"]
            entry["base"] += row["base"]
    ranked = sorted(customers.values(), key=lambda c: -c["base"])
    return {
        "base": s(base),
        "by_currency": {c: s(v) for c, v in sorted(by_currency.items())},
        "count": len(customers),
        "top": [
            {"id": c["id"], "name": c["name"], "base": s(c["base"]), "by_currency": {k: s(v) for k, v in c["by_currency"].items()}}
            for c in ranked[:limit]
            if c["base"] > 0
        ],
    }


def payables(scope, limit=None):
    purchases = scope.scoped(Purchase.objects.exclude(status=Purchase.Status.CANCELLED).filter(paid_amount__lt=F("total")))
    by_currency, base, suppliers = defaultdict(Decimal), ZERO, {}
    for row in purchases.values("supplier_id", "supplier__name", "currency").annotate(
        due=Sum(F("total") - F("paid_amount")), base=Sum(DUE_BASE)
    ):
        by_currency[row["currency"]] += row["due"]
        base += row["base"]
        entry = suppliers.setdefault(
            row["supplier_id"],
            {"id": str(row["supplier_id"]), "name": row["supplier__name"], "by_currency": defaultdict(Decimal), "base": ZERO},
        )
        entry["by_currency"][row["currency"]] += row["due"]
        entry["base"] += row["base"]
    ranked = sorted(suppliers.values(), key=lambda c: -c["base"])
    return {
        "base": s(base),
        "by_currency": {c: s(v) for c, v in sorted(by_currency.items())},
        "count": len(suppliers),
        "top": [
            {"id": c["id"], "name": c["name"], "base": s(c["base"]), "by_currency": {k: s(v) for k, v in c["by_currency"].items()}}
            for c in ranked[:limit]
            if c["base"] > 0
        ],
    }


def stock_summary(scope, *, with_value):
    """Low/out-of-stock counts (same rule as the Inventory screen) and, for cost viewers, stock value."""
    from apps.catalog.models import ProductVariant

    in_branches = Q(stock_balances__branch_id__in=scope.branch_ids)
    variants = ProductVariant.objects.filter(
        product__organization_id=scope.organization_id,
        product__section_id__in=scope.section_ids,
        product__tracks_stock=True,
        product__status="active",
        active=True,
    ).annotate(on_hand=Coalesce(Sum("stock_balances__quantity", filter=in_branches), ZERO, output_field=BIG))
    result = {
        "low_count": variants.filter(on_hand__gt=0, on_hand__lte=F("product__minimum_stock")).count(),
        "out_count": variants.filter(on_hand__lte=0).count(),
    }
    if with_value:
        balances = StockBalance.objects.filter(
            organization_id=scope.organization_id,
            branch_id__in=scope.branch_ids,
            variant__product__section_id__in=scope.section_ids,
            variant__product__tracks_stock=True,
        )
        result["value_base"] = s(_sum(balances, ExpressionWrapper(F("quantity") * F("average_cost_base"), output_field=BIG)))
        result["basis"] = "moving weighted-average cost"
    return result


def order_counts(scope):
    today = timezone.localdate()
    open_orders = scope.scoped(CustomOrder.objects.exclude(status__in=CLOSED_STATUSES))
    return {
        "active": open_orders.count(),
        "due_today": open_orders.filter(due_date=today).count(),
        "due_soon": open_orders.filter(due_date__gt=today, due_date__lte=today + timedelta(days=3)).count(),
        "overdue": open_orders.filter(due_date__lt=today).count(),
    }


def best_products(scope, limit=10):
    """Best sellers by revenue (USD base). Sale-level discounts are spread over lines by value."""
    lines = (
        SaleLine.objects.filter(sale__in=sales_in(scope))
        .select_related("sale", "product", "variant")
        .only(
            "quantity",
            "line_total",
            "unit_cost_base",
            "product__name",
            "variant__code",
            "variant__size",
            "variant__color",
            "sale__total",
            "sale__subtotal",
            "sale__line_discount_total",
            "sale__fx_units_per_usd",
        )
    )
    rows = {}
    for line in lines:
        sale = line.sale
        net_lines = sale.subtotal - sale.line_discount_total
        share = (sale.total / net_lines) if net_lines else ZERO
        revenue = line.line_total * share / sale.fx_units_per_usd
        key = (line.product_id, line.variant_id)
        label = line.product.name
        if line.variant_id and line.variant.code != "default":
            label += " · " + (" / ".join(p for p in (line.variant.size, line.variant.color) if p) or line.variant.code)
        row = rows.setdefault(key, {"product": str(line.product_id), "label": label, "quantity": ZERO, "revenue": ZERO, "cost": ZERO})
        row["quantity"] += line.quantity
        row["revenue"] += revenue
        row["cost"] += (line.unit_cost_base or ZERO) * line.quantity
    ranked = sorted(rows.values(), key=lambda r: -r["revenue"])[:limit]
    return [
        {
            "product": r["product"],
            "label": r["label"],
            "quantity": f"{r['quantity'].normalize():f}",
            "revenue_base": s(r["revenue"]),
            "cost_base": s(r["cost"]),
            "profit_base": s(r["revenue"] - r["cost"]),
        }
        for r in ranked
    ]


def best_customers(scope, limit=10):
    totals = defaultdict(lambda: {"revenue": ZERO, "count": 0, "name": ""})
    for qs in (sales_in(scope).filter(customer__isnull=False), delivered_orders_in(scope)):
        for row in qs.values("customer_id", "customer__name").annotate(t=Sum("base_total"), n=Count("id")):
            entry = totals[row["customer_id"]]
            entry["revenue"] += row["t"]
            entry["count"] += row["n"]
            entry["name"] = row["customer__name"]
    ranked = sorted(totals.items(), key=lambda kv: -kv[1]["revenue"])[:limit]
    return [{"id": str(cid), "name": e["name"], "revenue_base": s(e["revenue"]), "transactions": e["count"]} for cid, e in ranked]


def expenses_by_category(scope):
    rows = expenses_in(scope).values("category_id", "category__name").annotate(t=Sum("base_amount")).order_by("-t")
    return [{"id": str(r["category_id"]), "name": r["category__name"], "base": s(r["t"])} for r in rows]


def stock_valuation(scope):
    rows = (
        StockBalance.objects.filter(
            organization_id=scope.organization_id,
            branch_id__in=scope.branch_ids,
            variant__product__section_id__in=scope.section_ids,
            variant__product__tracks_stock=True,
        )
        .values("variant__product__section__name", "variant__product__category__name")
        .annotate(qty=Sum("quantity"), value=Sum(ExpressionWrapper(F("quantity") * F("average_cost_base"), output_field=BIG)))
        .order_by("variant__product__section__name", "variant__product__category__name")
    )
    return [
        {
            "section": r["variant__product__section__name"],
            "category": r["variant__product__category__name"] or "Uncategorised",
            "quantity": f"{r['qty'].normalize():f}",
            "value_base": s(r["value"]),
        }
        for r in rows
        if r["qty"]
    ]


def recent_activity(scope, *, sales=True, payments=True, orders=True, limit=8):
    items = []
    if sales:
        for sale in scope.scoped(Sale.objects.all()).select_related("customer", "section").order_by("-posted_at")[:limit]:
            items.append(
                {
                    "kind": "sale",
                    "id": str(sale.pk),
                    "number": sale.number,
                    "at": sale.posted_at.isoformat(),
                    "who": sale.customer.name if sale.customer_id else "Walk-in customer",
                    "section": sale.section.name,
                    "amount": str(sale.total),
                    "currency": sale.currency,
                    "base": str(sale.base_total),
                    "status": sale.status,
                }
            )
    if payments:
        allocations = (
            CustomerPaymentAllocation.objects.filter(
                Q(sale__section_id__in=scope.section_ids, sale__branch_id__in=scope.branch_ids)
                | Q(custom_order__section_id__in=scope.section_ids, custom_order__branch_id__in=scope.branch_ids),
                payment__organization_id=scope.organization_id,
            )
            .select_related("payment__customer", "sale__section", "custom_order__section")
            .order_by("-payment__received_at")[:limit]
        )
        for a in allocations:
            p, target = a.payment, a.target
            items.append(
                {
                    "kind": "payment",
                    "id": str(p.pk),
                    "number": p.number,
                    "at": p.received_at.isoformat(),
                    "who": p.customer.name if p.customer_id else "Walk-in customer",
                    "section": target.section.name,
                    "detail": f"for {target.number}",
                    "amount": str(a.amount),
                    "currency": p.currency,
                    "base": s(a.amount / p.fx_units_per_usd),
                    "status": p.status,
                }
            )
    if orders:
        for order in scope.scoped(CustomOrder.objects.all()).select_related("customer", "section").order_by("-created_at")[:limit]:
            items.append(
                {
                    "kind": "order",
                    "id": str(order.pk),
                    "number": order.number,
                    "at": order.created_at.isoformat(),
                    "who": order.customer.name,
                    "section": order.section.name,
                    "detail": order.title,
                    "amount": str(order.total),
                    "currency": order.currency,
                    "base": str(order.base_total),
                    "status": order.status,
                }
            )
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]
