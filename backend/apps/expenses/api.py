from rest_framework import mixins, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated

from apps.expenses.models import Expense, ExpenseCategory
from apps.expenses.serializers import ExpenseCategorySerializer, ExpenseSerializer
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import resolve_membership, scope_queryset


class ScopedExpenseViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    filter_backends = [SearchFilter]
    read_permission = None
    create_permission = None
    update_permission = None

    def get_required_permission(self, _request):
        return {"list": self.read_permission, "retrieve": self.read_permission,
                "create": self.create_permission, "update": self.update_permission,
                "partial_update": self.update_permission}.get(getattr(self, "action", None))

    def get_membership(self):
        if not hasattr(self.request, "membership"):
            self.request.membership = resolve_membership(self.request.user, self.request.headers.get("X-Organization-ID"))
        return self.request.membership

    def perform_create(self, serializer):
        serializer.save(organization=self.get_membership().organization)


class ExpenseCategoryViewSet(ScopedExpenseViewSet):
    serializer_class = ExpenseCategorySerializer
    read_permission = "expenses.view"
    create_permission = "expenses.create"
    update_permission = "expenses.manage"

    def get_queryset(self):
        return ExpenseCategory.objects.filter(organization_id=self.get_membership().organization_id)


class ExpenseViewSet(ScopedExpenseViewSet):
    serializer_class = ExpenseSerializer
    read_permission = "expenses.view"
    create_permission = "expenses.create"
    update_permission = "expenses.manage"
    search_fields = ("description", "category__name")

    def get_queryset(self):
        return scope_queryset(Expense.objects.all(), self.get_membership()).select_related("category", "section", "branch")

    def perform_create(self, serializer):
        serializer.save(organization=self.get_membership().organization, recorded_by=self.request.user, status=Expense.Status.DRAFT)
