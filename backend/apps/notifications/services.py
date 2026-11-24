"""In-app alerts (REQ-027), computed from current data and limited to what the person may see.

Kinds:
* stock_out / stock_low   inventory.view, own sections
* order_overdue / order_due / shoot_soon   orders.view, own sections and branches
* receivable   sales.view: a customer whose oldest unpaid invoice/order is older than RECEIVABLE_DAYS
* payable      purchases.view: goods received but unpaid for longer than PAYABLE_DAYS
* fx_rate      fx.manage: today's LRD rate has not been entered
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import F, Q, Sum
from django.utils import timezone

from apps.catalog.models import ProductVariant
from apps.currencies.models import ExchangeRate
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, has_permission
from apps.notifications.models import AlertRead
from apps.orders.models import CLOSED_STATUSES, CustomOrder
from apps.purchasing.models import Purchase
from apps.sales.models import Sale

RECEIVABLE_DAYS = 14
PAYABLE_DAYS = 30
DUE_SOON_DAYS = 1  # today and tomorrow
SHOOT_SOON_DAYS = 2
MAX_PER_KIND = 15
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


def _days(n):
    return f"{n} day{'' if n == 1 else 's'}"


def _money(amount, currency):
    return f"{currency} {amount:,.2f}"


def build_alerts(membership, user):
    today = timezone.localdate()
    org_id = membership.organization_id
    sections, branches = allowed_section_ids(membership), allowed_branch_ids(membership)
    can = lambda code: has_permission(membership, code)  # noqa: E731
    alerts = []

    def add(key, kind, severity, title, detail, page, *, record=None, query=None, when=None):
        alerts.append(
            {
                "key": key,
                "kind": kind,
                "severity": severity,
                "title": title,
                "detail": detail,
                "link": {"page": page, "id": record, "query": query},
                "date": (when or today).isoformat(),
            }
        )

    if can("fx.manage"):
        latest = ExchangeRate.objects.filter(organization_id=org_id, currency="LRD").order_by("-effective_date", "-created_at").first()
        if latest is None or latest.effective_date < today:
            add(
                f"fx_rate:{today}",
                "fx_rate",
                "warning",
                "Enter today's LRD rate",
                f"LRD sales are using the rate from {latest.effective_date:%d %b} ({latest.units_per_usd.normalize():f} per USD)."
                if latest
                else "No LRD exchange rate has been entered yet, so LRD sales cannot be recorded.",
                "sales",
            )

    if can("inventory.view"):
        in_branches = Q(stock_balances__branch_id__in=branches)
        variants = ProductVariant.objects.filter(
            product__organization_id=org_id,
            product__section_id__in=sections,
            product__tracks_stock=True,
            product__status="active",
            active=True,
        ).annotate(on_hand=Sum("stock_balances__quantity", filter=in_branches))
        variants = variants.select_related("product")
        out = [v for v in variants.filter(Q(on_hand__lte=0) | Q(on_hand__isnull=True))[:MAX_PER_KIND]]
        low = [v for v in variants.filter(on_hand__gt=0, on_hand__lte=F("product__minimum_stock"))[:MAX_PER_KIND]]
        for v in out:
            add(
                f"stock_out:{v.pk}",
                "stock_out",
                "critical",
                f"{_label(v)} is out of stock",
                "Restock or switch it off in Products.",
                "inventory",
                query=v.product.name,
            )
        for v in low:
            add(
                f"stock_low:{v.pk}:{v.on_hand.normalize():f}",
                "stock_low",
                "warning",
                f"{_label(v)} is running low",
                f"{v.on_hand.normalize():f} left (minimum {v.product.minimum_stock.normalize():f}).",
                "inventory",
                query=v.product.name,
            )

    if can("orders.view"):
        orders = (
            CustomOrder.objects.filter(organization_id=org_id, section_id__in=sections, branch_id__in=branches)
            .exclude(status__in=CLOSED_STATUSES)
            .select_related("customer", "photography")
        )
        for o in orders.filter(due_date__lt=today).order_by("due_date")[:MAX_PER_KIND]:
            late = (today - o.due_date).days
            add(
                f"order_overdue:{o.pk}:{o.due_date}",
                "order_overdue",
                "critical",
                f"{o.number} is {_days(late)} late",
                f"{o.title} for {o.customer.name} · {o.status_label}{_mine(o, user)}",
                "orders",
                record=str(o.pk),
                when=o.due_date,
            )
        for o in orders.filter(due_date__gte=today, due_date__lte=today + timedelta(days=DUE_SOON_DAYS)).order_by("due_date")[
            :MAX_PER_KIND
        ]:
            when = "today" if o.due_date == today else "tomorrow"
            add(
                f"order_due:{o.pk}:{o.due_date}",
                "order_due",
                "warning",
                f"{o.number} is due {when}",
                f"{o.title} for {o.customer.name} · {o.status_label}{_mine(o, user)}",
                "orders",
                record=str(o.pk),
                when=o.due_date,
            )
        start = timezone.now()
        for o in orders.filter(
            kind="photography", photography__shoot_at__gte=start, photography__shoot_at__lt=start + timedelta(days=SHOOT_SOON_DAYS)
        ).order_by("photography__shoot_at")[:MAX_PER_KIND]:
            shoot = timezone.localtime(o.photography.shoot_at)
            add(
                f"shoot_soon:{o.pk}:{shoot:%Y-%m-%dT%H:%M}",
                "shoot_soon",
                "info",
                f"Shoot {shoot:%a %d %b, %H:%M}: {o.customer.name}",
                f"{o.title}{' · ' + o.photography.location if o.photography.location else ''}{_mine(o, user)}",
                "orders",
                record=str(o.pk),
                when=shoot.date(),
            )

    if can("sales.view"):
        cutoff = timezone.now() - timedelta(days=RECEIVABLE_DAYS)
        oldest, owed = {}, defaultdict(lambda: defaultdict(int))
        docs = [
            *Sale.objects.filter(
                organization_id=org_id,
                section_id__in=sections,
                branch_id__in=branches,
                status="posted",
                paid_amount__lt=F("total"),
                customer__isnull=False,
            ).values("customer_id", "customer__name", "currency", "total", "paid_amount", "posted_at", "id"),
            *CustomOrder.objects.filter(organization_id=org_id, section_id__in=sections, branch_id__in=branches, paid_amount__lt=F("total"))
            .exclude(status="cancelled")
            .values("customer_id", "customer__name", "currency", "total", "paid_amount", "created_at", "id"),
        ]
        for d in docs:
            when = d.get("posted_at") or d.get("created_at")
            owed[d["customer_id"]][d["currency"]] += d["total"] - d["paid_amount"]
            if d["customer_id"] not in oldest or when < oldest[d["customer_id"]][0]:
                oldest[d["customer_id"]] = (when, d["id"], d["customer__name"])
        late = sorted((v for v in oldest.items() if v[1][0] < cutoff), key=lambda kv: kv[1][0])[:MAX_PER_KIND]
        for customer_id, (when, doc_id, name) in late:
            age = (timezone.now() - when).days
            amounts = " · ".join(_money(v, c) for c, v in sorted(owed[customer_id].items()))
            add(
                f"receivable:{customer_id}:{doc_id}",
                "receivable",
                "warning",
                f"{name} owes {amounts}",
                f"Oldest unpaid item is {_days(age)} old.",
                "customers",
                query=name,
                when=timezone.localtime(when).date(),
            )

    if can("purchases.view"):
        cutoff = today - timedelta(days=PAYABLE_DAYS)
        for p in (
            Purchase.objects.filter(
                organization_id=org_id,
                section_id__in=sections,
                branch_id__in=branches,
                status__in=["partially_received", "received"],
                paid_amount__lt=F("total"),
                purchase_date__lt=cutoff,
            )
            .select_related("supplier")
            .order_by("purchase_date")[:MAX_PER_KIND]
        ):
            add(
                f"payable:{p.pk}",
                "payable",
                "info",
                f"{p.supplier.name}: {_money(p.total - p.paid_amount, p.currency)} unpaid",
                f"{p.number} from {p.purchase_date:%d %b} ({_days((today - p.purchase_date).days)} ago).",
                "purchases",
                record=str(p.pk),
                when=p.purchase_date,
            )

    if can("website.manage"):
        from apps.public_site.models import WebsiteRequest

        for r in WebsiteRequest.objects.filter(organization_id=org_id, status=WebsiteRequest.Status.NEW).order_by("-created_at")[:10]:
            add(
                f"website_request:{r.pk}",
                "website_request",
                "warning",
                f"Website request from {r.name}",
                f"{r.number} · {r.get_kind_display()} · reply on {r.phone}",
                "website",
                record=str(r.pk),
                when=timezone.localtime(r.created_at).date(),
            )

    alerts.sort(key=lambda a: (SEVERITY_ORDER[a["severity"]], a["date"]))
    read = set(
        AlertRead.objects.filter(organization_id=org_id, user=user, key__in=[a["key"] for a in alerts]).values_list("key", flat=True)
    )
    for alert in alerts:
        alert["read"] = alert["key"] in read
    return alerts


def _label(variant):
    options = " / ".join(p for p in (variant.size, variant.color) if p)
    return variant.product.name if variant.code == "default" and not options else f"{variant.product.name} ({options or variant.code})"


def _mine(order, user):
    return " · assigned to you" if order.assigned_to_id == user.pk else ""


def mark_read(membership, user, keys):
    AlertRead.objects.bulk_create(
        [AlertRead(organization_id=membership.organization_id, user=user, key=k[:160]) for k in keys], ignore_conflicts=True
    )
