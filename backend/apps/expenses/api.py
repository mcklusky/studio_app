from decimal import Decimal

from django.db.models import Sum
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.filters import date_param
from apps.common.idempotency import run_idempotent
from apps.common.viewsets import ScopedViewSet
from apps.expenses import services
from apps.expenses.models import Expense, ExpenseCategory
from apps.expenses.serializers import ExpenseCategorySerializer, ExpenseInputSerializer, ExpenseSerializer
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import scope_queryset


class ExpenseCategoryViewSet(ScopedViewSet):
    serializer_class = ExpenseCategorySerializer
    read_permission = "expenses.view"
    create_permission = "expenses.create"
    update_permission = "expenses.manage"

    def get_queryset(self):
        return ExpenseCategory.objects.filter(organization_id=self.get_membership().organization_id)


class ExpenseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Expenses are recorded (posted) once; corrections are reversals."""

    permission_classes = [IsAuthenticated, HasBusinessPermission]
    serializer_class = ExpenseSerializer
    filter_backends = [SearchFilter]
    search_fields = ("number", "description", "category__name", "reference")
    PERMISSIONS = {"list": "expenses.view", "retrieve": "expenses.view", "create": "expenses.create", "reverse": "expenses.manage"}

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_queryset(self):
        queryset = scope_queryset(Expense.objects.all(), self.request.membership).select_related(
            "category", "section", "recorded_by", "reversed_by"
        )
        params = self.request.query_params
        for param, field in (("status", "status"), ("category", "category_id"), ("section", "section_id"), ("currency", "currency")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        start, end = date_param(self.request, "from"), date_param(self.request, "to")
        if start:
            queryset = queryset.filter(expense_date__gte=start)
        if end:
            queryset = queryset.filter(expense_date__lte=end)
        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        posted = self.filter_queryset(self.get_queryset()).filter(status=Expense.Status.POSTED)
        cents = Decimal("0.01")
        by_currency = {
            row["currency"]: str(row["total"].quantize(cents)) for row in posted.values("currency").annotate(total=Sum("amount"))
        }
        response.data["totals"] = {
            "by_currency": by_currency,
            "base_total": str((posted.aggregate(t=Sum("base_amount"))["t"] or Decimal("0")).quantize(cents)),
        }
        return response

    def create(self, request):
        serializer = ExpenseInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        organization = request.membership.organization

        def handler():
            expense = services.record_expense(organization=organization, actor=request.user, request=request, **serializer.validated_data)
            return Response(ExpenseSerializer(expense).data, status=201)

        return run_idempotent(request, organization=organization, scope="expenses.create", handler=handler, required=True)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        expense = services.reverse_expense(
            self.get_object(), actor=request.user, reason=str(request.data.get("reason", "")), request=request
        )
        return Response(ExpenseSerializer(expense).data)
