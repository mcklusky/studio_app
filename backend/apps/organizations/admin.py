from django.contrib import admin

from apps.organizations.models import Branch, BusinessSection, Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "base_currency", "timezone", "active")
    search_fields = ("name",)


@admin.register(BusinessSection)
class BusinessSectionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "active")
    list_filter = ("organization", "active")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "active")
    list_filter = ("organization", "active")
