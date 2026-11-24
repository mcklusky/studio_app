from django.contrib import admin

from apps.catalog.models import Category, Customer, Product, ProductVariant, Supplier


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "customer_type", "phone", "organization", "active")
    list_filter = ("organization", "customer_type", "active")
    search_fields = ("name", "phone", "email")


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "organization", "active")
    list_filter = ("organization", "active")
    search_fields = ("name", "phone", "email")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "section", "active")
    list_filter = ("organization", "section", "active")


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "section", "kind", "status", "organization")
    list_filter = ("organization", "section", "kind", "status")
    search_fields = ("name", "sku")
    inlines = (ProductVariantInline,)
