from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.catalog.api import CategoryViewSet, CustomerViewSet, ProductVariantViewSet, ProductViewSet, SupplierViewSet
from apps.expenses.api import ExpenseCategoryViewSet, ExpenseViewSet
from apps.identity.views import BranchListView, CurrentUserView, LoginView, LogoutView, OrganizationView, PasswordResetRequestView, SectionListView, csrf_cookie

def health(_request):
    return JsonResponse({"status": "ok", "service": "studio-api"})


router = SimpleRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("product-variants", ProductVariantViewSet, basename="product-variant")
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("expenses", ExpenseViewSet, basename="expense")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/csrf/", csrf_cookie, name="csrf-cookie"),
    path("api/v1/auth/login/", LoginView.as_view(), name="login"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/v1/auth/password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("api/v1/auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("api/v1/organization/", OrganizationView.as_view(), name="organization"),
    path("api/v1/business-sections/", SectionListView.as_view(), name="business-sections"),
    path("api/v1/branches/", BranchListView.as_view(), name="branches"),
    path("api/v1/", include(router.urls)),
]
