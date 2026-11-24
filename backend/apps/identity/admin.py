from django.contrib import admin

from apps.identity.models import AccessPermission, Membership, Role


@admin.register(AccessPermission)
class AccessPermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "is_system")
    list_filter = ("organization", "is_system")
    filter_horizontal = ("permissions",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "active", "all_sections", "all_branches")
    list_filter = ("organization", "role", "active")
    filter_horizontal = ("sections", "branches")
