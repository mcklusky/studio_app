from rest_framework import mixins, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from apps.catalog.models import Category, Customer, Product, ProductVariant, Supplier
from apps.catalog.serializers import CategorySerializer, CustomerSerializer, ProductSerializer, ProductVariantSerializer, SupplierSerializer
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import allowed_section_ids, resolve_membership, scope_queryset


class ScopedViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
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


class CustomerViewSet(ScopedViewSet):
    serializer_class = CustomerSerializer
    read_permission = "customers.view"
    create_permission = "customers.create"
    update_permission = "customers.manage"
    search_fields = ("name", "phone", "email")

    def get_queryset(self):
        return Customer.objects.filter(organization_id=self.get_membership().organization_id).order_by("name")


class SupplierViewSet(ScopedViewSet):
    serializer_class = SupplierSerializer
    read_permission = "suppliers.view"
    create_permission = "suppliers.create"
    update_permission = "suppliers.manage"
    search_fields = ("name", "phone", "email", "location")

    def get_queryset(self):
        return Supplier.objects.filter(organization_id=self.get_membership().organization_id).order_by("name")


class CategoryViewSet(ScopedViewSet):
    serializer_class = CategorySerializer
    read_permission = "catalog.view"
    create_permission = "catalog.create"
    update_permission = "catalog.manage"
    search_fields = ("name",)

    def get_queryset(self):
        membership = self.get_membership()
        sections = allowed_section_ids(membership)
        return Category.objects.filter(organization_id=membership.organization_id).filter(
            Q(section__isnull=True) | Q(section_id__in=sections)
        ).order_by("name")


class ProductViewSet(ScopedViewSet):
    serializer_class = ProductSerializer
    read_permission = "catalog.view"
    create_permission = "catalog.create"
    update_permission = "catalog.manage"
    search_fields = ("name", "sku")
    def get_queryset(self):
        return scope_queryset(Product.objects.all(), self.get_membership()).select_related("section", "category")

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        for key in ("section", "category", "status", "kind"):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{f"{key}_id" if key in ("section", "category") else key: value})
        return queryset


class ProductVariantViewSet(ScopedViewSet):
    serializer_class = ProductVariantSerializer
    read_permission = "catalog.view"
    create_permission = "catalog.create"
    update_permission = "catalog.manage"
    
    def get_queryset(self):
        membership = self.get_membership()
        return ProductVariant.objects.filter(product__organization_id=membership.organization_id,
            product__section_id__in=allowed_section_ids(membership)).select_related("product")

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]
        membership = self.get_membership()
        if product.organization_id != membership.organization_id or product.section_id not in allowed_section_ids(membership):
            from rest_framework.exceptions import NotFound
            raise NotFound()
        serializer.save()
