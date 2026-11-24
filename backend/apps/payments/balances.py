"""Outstanding balances, kept per currency (LRD and USD are never added together)."""

from collections import defaultdict
from decimal import Decimal

from django.db.models import F, Sum


def _per_currency(rows, key):
    totals = defaultdict(lambda: defaultdict(Decimal))
    for row in rows:
        if row["due"]:
            totals[row[key]][row["currency"]] += row["due"]
    return {
        owner: {c: str(v.quantize(Decimal("0.01"))) for c, v in by_currency.items() if v > 0}
        for owner, by_currency in totals.items()
        if any(v > 0 for v in by_currency.values())
    }


def customer_balances(sales_queryset, customer_ids, orders_queryset=None):
    """{customer_id: {"USD": "12.00", "LRD": "500.00"}}: unpaid posted sales plus unpaid, uncancelled
    department orders in the given scope."""
    rows = list(
        sales_queryset.filter(customer_id__in=customer_ids, status="posted")
        .values("customer_id", "currency")
        .annotate(due=Sum(F("total") - F("paid_amount")))
    )
    if orders_queryset is not None:
        rows += list(
            orders_queryset.filter(customer_id__in=customer_ids)
            .exclude(status="cancelled")
            .values("customer_id", "currency")
            .annotate(due=Sum(F("total") - F("paid_amount")))
        )
    return _per_currency(rows, "customer_id")


def supplier_balances(purchases_queryset, supplier_ids):
    rows = (
        purchases_queryset.filter(supplier_id__in=supplier_ids)
        .exclude(status="cancelled")
        .values("supplier_id", "currency")
        .annotate(due=Sum(F("total") - F("paid_amount")))
    )
    return _per_currency(rows, "supplier_id")
