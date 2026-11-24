"""Dashboard and report endpoints. Figures are included only for roles allowed to see them."""

from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.audit.services import record_event
from apps.common.filters import date_param
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import has_permission
from apps.organizations.models import Branch, BusinessSection
from apps.reports import exports, services

BASIS = (
    "USD reporting base. LRD amounts are converted with the exchange rate saved on each transaction "
    "(the owner/admin daily rate in force on its date), rounded half-up to cents. LRD and USD subtotals are shown separately."
)
DEFINITIONS = {
    "sales": "Posted sales by posting date; reversed sales excluded.",
    "orders_delivered": "Department orders delivered in the period, at their agreed price (provisional policy).",
    "cash_collected": "Customer payments received in the period (deposits included), net of reversals.",
    "purchases": "Supplier purchases by purchase date, excluding cancelled. Not an expense; stock cost reaches profit when sold.",
    "expenses": "Posted operating expenses by expense date.",
    "gross_profit": "Sales + orders delivered − cost of goods sold (weighted-average cost, plus stock materials used on delivered orders).",
    "net_profit": "Gross profit − expenses.",
}


class ReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    PERMISSIONS = {
        "dashboard": "dashboard.view",
        "summary": "reports.view",
        "products": "reports.view",
        "customers": "reports.view",
        "debts": "reports.view",
        "stock": "reports.view",
        "export": "reports.view",
    }

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def can(self, code):
        return has_permission(self.request.membership, code)

    def scope(self):
        params = self.request.query_params
        return services.build_scope(
            self.request.membership,
            start=date_param(self.request, "from"),
            end=date_param(self.request, "to"),
            section=params.get("section"),
            branch=params.get("branch"),
        )

    def meta(self, scope):
        section = (
            BusinessSection.objects.filter(pk=self.request.query_params.get("section")).first()
            if self.request.query_params.get("section")
            else None
        )
        branch = (
            Branch.objects.filter(pk=self.request.query_params.get("branch")).first() if self.request.query_params.get("branch") else None
        )
        return {
            "period": {"from": scope.start.isoformat(), "to": scope.end.isoformat(), "days": scope.days},
            "section": {"id": str(section.pk), "name": section.name} if section else None,
            "branch": {"id": str(branch.pk), "name": branch.name} if branch else None,
            "base_currency": "USD",
            "basis": BASIS,
        }

    def _financial_view(self, scope, figures):
        """Drop the figures this role may not see."""
        visible = {}
        if self.can("sales.view"):
            for key in ("sales", "orders_delivered", "revenue_base", "cash_collected"):
                visible[key] = figures[key]
        if self.can("expenses.view"):
            visible["expenses"] = figures["expenses"]
        if self.can("purchases.view"):
            visible["purchases"] = figures["purchases"]
        if self.can("reports.view") and self.can("inventory.costs"):
            for key in ("cost_of_goods_sold_base", "gross_profit_base", "net_profit_base"):
                visible[key] = figures[key]
        return visible

    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        scope = self.scope()
        sales_ok, orders_ok = self.can("sales.view"), self.can("orders.view")
        data = {**self.meta(scope), "figures": self._financial_view(scope, services.financials(scope))}
        if sales_ok:
            previous = services.financials(scope.previous())
            data["previous"] = {
                "period": {"from": scope.previous().start.isoformat(), "to": scope.previous().end.isoformat()},
                "revenue_base": previous["revenue_base"],
                "cash_collected_base": previous["cash_collected"]["base"],
            }
            data["series"] = services.daily_series(scope) if scope.days <= 92 else None
            data["by_section"] = services.by_section(scope)
            data["receivables"] = services.receivables(scope, limit=5)
        if self.can("purchases.view"):
            data["payables"] = services.payables(scope, limit=5)
        if self.can("inventory.view"):
            data["stock"] = services.stock_summary(scope, with_value=self.can("inventory.costs"))
        if orders_ok:
            data["orders"] = services.order_counts(scope)
        if sales_ok or orders_ok:
            data["recent"] = services.recent_activity(scope, sales=sales_ok, payments=sales_ok, orders=orders_ok)
        if not self.can("expenses.view"):
            for row in data.get("by_section", []):
                row.pop("expenses_base", None)
        return Response(data)

    def _summary_payload(self, scope):
        figures = services.financials(scope)
        previous = services.financials(scope.previous())
        return {
            **self.meta(scope),
            "definitions": DEFINITIONS,
            "figures": self._financial_view(scope, figures),
            "previous": {
                "from": scope.previous().start.isoformat(),
                "to": scope.previous().end.isoformat(),
                "figures": self._financial_view(scope.previous(), previous),
            },
            "by_section": [
                row if self.can("expenses.view") else {k: v for k, v in row.items() if k != "expenses_base"}
                for row in services.by_section(scope)
            ],
            "expenses_by_category": services.expenses_by_category(scope) if self.can("expenses.view") else [],
            "series": services.daily_series(scope) if scope.days <= 92 else None,
        }

    @action(detail=False, methods=["get"])
    def summary(self, request):
        return Response(self._summary_payload(self.scope()))

    @action(detail=False, methods=["get"], url_path=r"(?P<report>summary|products|customers|debts|stock)/export")
    def export(self, request, report=None):
        """Download a report as .xlsx or .pdf, with the same filters and figures as the screen."""
        fmt = request.query_params.get("file", "xlsx")
        if fmt not in ("xlsx", "pdf"):
            raise ValidationError({"file": ["Choose xlsx or pdf."]})
        if report == "stock" and not self.can("inventory.costs"):
            raise PermissionDenied("Stock value needs permission to see inventory costs.")
        scope = self.scope()
        meta = self.meta(scope)
        document = exports.build_document(report, scope, self, meta)
        content = exports.render_xlsx(document) if fmt == "xlsx" else exports.render_pdf(document)
        record_event(
            organization=request.membership.organization,
            action="report.exported",
            entity=request.membership.organization,
            request=request,
            summary={
                "report": report,
                "format": fmt,
                "from": meta["period"]["from"],
                "to": meta["period"]["to"],
                "section": meta["section"]["name"] if meta["section"] else "all",
            },
        )
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "application/pdf"
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{exports.filename(document, meta, fmt)}"'
        response["Cache-Control"] = "private, no-store"
        return response

    @action(detail=False, methods=["get"])
    def products(self, request):
        scope = self.scope()
        rows = services.best_products(scope, limit=min(int(request.query_params.get("limit", 20) or 20), 100))
        if not self.can("inventory.costs"):
            for row in rows:
                row.pop("cost_base"), row.pop("profit_base")
        return Response({**self.meta(scope), "rows": rows})

    @action(detail=False, methods=["get"])
    def customers(self, request):
        scope = self.scope()
        return Response({**self.meta(scope), "rows": services.best_customers(scope, limit=20)})

    @action(detail=False, methods=["get"])
    def debts(self, request):
        scope = self.scope()
        data = {**self.meta(scope)}
        if self.can("sales.view"):
            data["receivables"] = services.receivables(scope)
        if self.can("purchases.view"):
            data["payables"] = services.payables(scope)
        return Response(data)

    @action(detail=False, methods=["get"])
    def stock(self, request):
        scope = self.scope()
        if not self.can("inventory.costs"):
            return Response({**self.meta(scope), "rows": [], "restricted": True})
        summary = services.stock_summary(scope, with_value=True)
        return Response({**self.meta(scope), "rows": services.stock_valuation(scope), **summary})
