from django.contrib import admin

from apps.orders.models import CustomOrder, OrderStatusEvent


class StatusEventInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "note", "is_correction", "actor", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CustomOrder)
class CustomOrderAdmin(admin.ModelAdmin):
    """Read-only: orders change through the app so status history and audit stay complete."""

    list_display = ("number", "kind", "customer", "status", "currency", "total", "paid_amount", "due_date")
    list_filter = ("kind", "status", "currency")
    search_fields = ("number", "title", "customer__name")
    inlines = [StatusEventInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
