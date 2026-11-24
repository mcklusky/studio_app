from django.conf import settings
from django.contrib import admin
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.audit.api import AuditEventViewSet
from apps.catalog.api import CategoryViewSet, CustomerViewSet, ProductVariantViewSet, ProductViewSet, SupplierViewSet
from apps.chat.api import ChatPeopleView, ConversationListView, ConversationReadView, MessageListView
from apps.currencies.api import ExchangeRateViewSet
from apps.expenses.api import ExpenseCategoryViewSet, ExpenseViewSet
from apps.files.api import AttachmentDetailView, AttachmentFileView, AttachmentListView
from apps.identity.staff import ChangePasswordView, RoleViewSet, StaffViewSet
from apps.identity.views import (
    BranchListView,
    CurrentUserView,
    LoginView,
    LogoutView,
    OrganizationView,
    PasswordResetRequestView,
    SectionListView,
    csrf_cookie,
)
from apps.inventory.api import StockAdjustmentViewSet, StockLevelViewSet, StockMovementViewSet
from apps.notifications.api import AlertsReadView, AlertsView
from apps.orders.api import OrderViewSet
from apps.payments.api import CustomerPaymentViewSet, SupplierPaymentViewSet
from apps.public_site.api import (
    PublicCatalogView,
    PublicProductImageView,
    PublicRequestView,
    PublicSiteView,
    PublicTrackView,
    WebsiteProfileView,
    WebsiteRequestActionView,
    WebsiteRequestListView,
)
from apps.purchasing.api import PurchaseViewSet
from apps.reports.api import ReportViewSet
from apps.sales.api import SaleViewSet
from apps.search.api import SearchView


def health(_request):
    """Liveness: the process answers."""
    return JsonResponse({"status": "ok", "service": "studio-api"})


def health_ready(_request):
    """Readiness: the database answers and private storage is writable. For uptime monitors."""
    from django.db import connection

    from apps.files.services import private_storage

    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001 - report, never raise, from a health check
        checks["database"] = "unavailable"
    try:
        storage = private_storage()
        name = storage.save(".health/probe.txt", ContentFile(b"ok"))
        storage.delete(name)
        checks["storage"] = "ok"
    except Exception:  # noqa: BLE001
        checks["storage"] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JsonResponse({"status": "ok" if healthy else "degraded", **checks}, status=200 if healthy else 503)


router = SimpleRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("categories", CategoryViewSet, basename="category")
router.register("products", ProductViewSet, basename="product")
router.register("product-variants", ProductVariantViewSet, basename="product-variant")
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("audit-events", AuditEventViewSet, basename="audit-event")
router.register("stock", StockLevelViewSet, basename="stock")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("stock-adjustments", StockAdjustmentViewSet, basename="stock-adjustment")
router.register("exchange-rates", ExchangeRateViewSet, basename="exchange-rate")
router.register("purchases", PurchaseViewSet, basename="purchase")
router.register("sales", SaleViewSet, basename="sale")
router.register("orders", OrderViewSet, basename="order")
router.register("reports", ReportViewSet, basename="report")
router.register("staff", StaffViewSet, basename="staff")
router.register("roles", RoleViewSet, basename="role")
router.register("customer-payments", CustomerPaymentViewSet, basename="customer-payment")
router.register("supplier-payments", SupplierPaymentViewSet, basename="supplier-payment")

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/health/ready/", health_ready, name="health-ready"),
    path("api/v1/auth/csrf/", csrf_cookie, name="csrf-cookie"),
    path("api/v1/auth/login/", LoginView.as_view(), name="login"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/v1/auth/password-reset/", PasswordResetRequestView.as_view(), name="password-reset"),
    path("api/v1/auth/me/", CurrentUserView.as_view(), name="current-user"),
    path("api/v1/auth/password/", ChangePasswordView.as_view(), name="change-password"),
    path("api/v1/organization/", OrganizationView.as_view(), name="organization"),
    path("api/v1/business-sections/", SectionListView.as_view(), name="business-sections"),
    path("api/v1/branches/", BranchListView.as_view(), name="branches"),
    path("api/v1/search/", SearchView.as_view(), name="search"),
    path("api/v1/attachments/", AttachmentListView.as_view(), name="attachments"),
    path("api/v1/attachments/<uuid:pk>/", AttachmentDetailView.as_view(), name="attachment"),
    path("api/v1/attachments/<uuid:pk>/file/", AttachmentFileView.as_view(), name="attachment-file"),
    path("api/v1/alerts/", AlertsView.as_view(), name="alerts"),
    path("api/v1/alerts/read/", AlertsReadView.as_view(), name="alerts-read"),
    path("api/v1/chat/conversations/", ConversationListView.as_view(), name="chat-conversations"),
    path("api/v1/chat/conversations/<uuid:pk>/messages/", MessageListView.as_view(), name="chat-messages"),
    path("api/v1/chat/conversations/<uuid:pk>/read/", ConversationReadView.as_view(), name="chat-read"),
    path("api/v1/chat/people/", ChatPeopleView.as_view(), name="chat-people"),
    path("api/v1/website/profile/", WebsiteProfileView.as_view(), name="website-profile"),
    path("api/v1/website/requests/", WebsiteRequestListView.as_view(), name="website-requests"),
    path("api/v1/website/requests/<uuid:pk>/<str:action>/", WebsiteRequestActionView.as_view(), name="website-request-action"),
    path("api/public/v1/site/", PublicSiteView.as_view(), name="public-site"),
    path("api/public/v1/catalog/", PublicCatalogView.as_view(), name="public-catalog"),
    path("api/public/v1/catalog/<uuid:pk>/image/", PublicProductImageView.as_view(), name="public-product-image"),
    path("api/public/v1/requests/", PublicRequestView.as_view(), name="public-requests"),
    path("api/public/v1/track/", PublicTrackView.as_view(), name="public-track"),
    path("api/v1/", include(router.urls)),
]
