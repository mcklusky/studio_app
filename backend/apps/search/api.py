"""Global search (REQ-026): one box, results grouped by record type.

Each group is searched only if the caller may see that kind of record, and
only within their sections and branches. Fields searched are an explicit
allow-list per group (never free-form lookups from the client). Each group
returns at most PER_GROUP rows plus whether more exist; the list pages carry
the full filters.
"""

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalog.models import Customer, Product, Supplier
from apps.expenses.models import Expense
from apps.identity.models import Membership
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, focus_on_view, has_permission, resolve_membership
from apps.orders.models import STATUS_LABELS, CustomOrder
from apps.payments.models import CustomerPayment
from apps.purchasing.models import Purchase
from apps.sales.models import Sale

PER_GROUP = 5
MIN_LENGTH = 2


def _match(fields, term):
    query = Q()
    for field in fields:
        query |= Q(**{f"{field}__icontains": term})
    return query


def _money(amount, currency):
    return f"{currency} {amount:,.2f}"


class SearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        request.membership = focus_on_view(membership, request)
        term = str(request.query_params.get("q", "")).strip()[:80]
        if len(term) < MIN_LENGTH:
            return Response({"query": term, "groups": []})
        org_id = membership.organization_id
        sections, branches = allowed_section_ids(membership), allowed_branch_ids(membership)
        can = lambda code: has_permission(membership, code)  # noqa: E731
        in_scope = {"organization_id": org_id, "section_id__in": sections, "branch_id__in": branches}
        groups = []

        def add(key, label, page, queryset, row):
            rows = list(queryset[: PER_GROUP + 1])
            if rows:
                groups.append(
                    {"key": key, "label": label, "page": page, "more": len(rows) > PER_GROUP, "results": [row(r) for r in rows[:PER_GROUP]]}
                )

        if can("sales.view"):
            add(
                "sales",
                "Sales",
                "sales",
                Sale.objects.filter(**in_scope)
                .filter(_match(("number", "customer__name", "customer__phone"), term))
                .select_related("customer")
                .order_by("-posted_at"),
                lambda s: {
                    "id": str(s.pk),
                    "title": s.number,
                    "subtitle": f"{s.customer.name if s.customer_id else 'Walk-in'} · {_money(s.total, s.currency)}"
                    f"{' · reversed' if s.status == 'reversed' else (' · balance due' if s.paid_amount < s.total else '')}",
                    "date": s.posted_at.date().isoformat(),
                },
            )
            payment_scope = Q(allocations__sale__section_id__in=sections, allocations__sale__branch_id__in=branches) | Q(
                allocations__custom_order__section_id__in=sections, allocations__custom_order__branch_id__in=branches
            )
            add(
                "payments",
                "Payments",
                "customers",
                CustomerPayment.objects.filter(payment_scope, organization_id=org_id)
                .filter(_match(("number", "reference", "customer__name"), term))
                .distinct()
                .select_related("customer")
                .order_by("-received_at"),
                lambda p: {
                    "id": str(p.pk),
                    "title": p.number,
                    "query": p.customer.name if p.customer_id else "",
                    "subtitle": f"{p.customer.name if p.customer_id else 'Walk-in'} · {_money(p.amount, p.currency)} · "
                    f"{p.get_method_display()}{' · reversed' if p.status == 'reversed' else ''}",
                    "date": p.received_at.date().isoformat(),
                },
            )
        if can("orders.view"):
            add(
                "orders",
                "Orders",
                "orders",
                CustomOrder.objects.filter(**in_scope)
                .filter(_match(("number", "title", "customer__name", "customer__phone"), term))
                .select_related("customer")
                .order_by("-created_at"),
                lambda o: {
                    "id": str(o.pk),
                    "title": f"{o.number} · {o.title}",
                    "subtitle": f"{o.customer.name} · {STATUS_LABELS.get(o.status, o.status)} · due {o.due_date:%d %b}",
                    "date": o.created_at.date().isoformat(),
                },
            )
        if can("customers.view"):
            add(
                "customers",
                "Customers",
                "customers",
                Customer.objects.filter(organization_id=org_id).filter(_match(("name", "phone", "email"), term)).order_by("name"),
                lambda c: {
                    "id": str(c.pk),
                    "title": c.name,
                    "query": c.name,
                    "subtitle": " · ".join(filter(None, [c.phone, c.email])) or "Customer",
                },
            )
        if can("catalog.view"):
            add(
                "products",
                "Products",
                "products",
                Product.objects.filter(organization_id=org_id, section_id__in=sections)
                .filter(_match(("name", "sku", "variants__code", "variants__size", "variants__color"), term))
                .distinct()
                .select_related("section")
                .order_by("name"),
                lambda p: {
                    "id": str(p.pk),
                    "title": p.name,
                    "query": p.name,
                    "subtitle": " · ".join(
                        filter(
                            None,
                            [
                                p.section.name,
                                p.sku,
                                "service" if p.kind == "service" else None,
                                "inactive" if p.status != "active" else None,
                            ],
                        )
                    ),
                },
            )
        if can("suppliers.view"):
            add(
                "suppliers",
                "Suppliers",
                "suppliers",
                Supplier.objects.filter(organization_id=org_id)
                .filter(_match(("name", "phone", "email", "location"), term))
                .order_by("name"),
                lambda s: {
                    "id": str(s.pk),
                    "title": s.name,
                    "query": s.name,
                    "subtitle": " · ".join(filter(None, [s.phone, s.location])) or "Supplier",
                },
            )
        if can("purchases.view"):
            add(
                "purchases",
                "Purchases",
                "purchases",
                Purchase.objects.filter(**in_scope)
                .filter(_match(("number", "supplier__name", "supplier_reference"), term))
                .select_related("supplier")
                .order_by("-purchase_date", "-created_at"),
                lambda p: {
                    "id": str(p.pk),
                    "title": p.number,
                    "subtitle": f"{p.supplier.name} · {_money(p.total, p.currency)} · {p.get_status_display()}",
                    "date": p.purchase_date.isoformat(),
                },
            )
        if can("expenses.view"):
            add(
                "expenses",
                "Expenses",
                "expenses",
                Expense.objects.filter(**in_scope)
                .filter(_match(("number", "description", "category__name", "reference"), term))
                .select_related("category")
                .order_by("-expense_date"),
                lambda e: {
                    "id": str(e.pk),
                    "title": f"{e.number} · {e.description}",
                    "query": e.number,
                    "subtitle": f"{e.category.name} · {_money(e.amount, e.currency)}{' · reversed' if e.status == 'reversed' else ''}",
                    "date": e.expense_date.isoformat(),
                },
            )
        if can("staff.manage"):
            add(
                "staff",
                "Staff",
                "team",
                Membership.objects.filter(organization_id=org_id)
                .filter(_match(("user__username", "user__first_name", "user__last_name", "user__email"), term))
                .select_related("user", "role")
                .order_by("user__first_name"),
                lambda m: {
                    "id": str(m.pk),
                    "title": m.user.get_full_name() or m.user.username,
                    "query": m.user.username,
                    "subtitle": f"{m.role.name} · {m.user.username}{'' if m.active else ' · deactivated'}",
                },
            )
        return Response({"query": term, "groups": groups})
