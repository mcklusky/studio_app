from uuid import UUID

from django.db.models import F, Q
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.catalog.models import Category, Customer, Product, ProductVariant, Supplier
from apps.catalog.serializers import CategorySerializer, CustomerSerializer, ProductSerializer, ProductVariantSerializer, SupplierSerializer
from apps.common.viewsets import ScopedViewSet
from apps.identity.scope import allowed_section_ids, has_permission, scope_queryset
from apps.inventory.services import ensure_default_variant
from apps.payments.balances import customer_balances, supplier_balances


class BalanceMixin:
    """Adds per-currency balances to list rows, a ?has_balance=true filter and a statement view,
    visible only to roles that can see the underlying sales/purchases."""

    balance_permission = None

    def shows_balances(self):
        return has_permission(self.get_membership(), self.balance_permission)

    def owners_with_balance(self):
        """Q filter selecting contacts that have something open."""
        raise NotImplementedError

    def balances_for(self, ids):
        raise NotImplementedError

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.request.query_params.get("has_balance") == "true" and self.shows_balances():
            queryset = queryset.filter(self.owners_with_balance())
        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if self.shows_balances():
            rows = response.data["results"]
            balances = self.balances_for([row["id"] for row in rows])
            for row in rows:
                row["balances"] = balances.get(UUID(str(row["id"])), {})
        return response


class CustomerViewSet(BalanceMixin, ScopedViewSet):
    serializer_class = CustomerSerializer
    read_permission = "customers.view"
    create_permission = "customers.create"
    update_permission = "customers.manage"
    extra_action_permissions = {"statement": "sales.view"}
    balance_permission = "sales.view"
    search_fields = ("name", "phone", "email")

    def get_queryset(self):
        return Customer.objects.filter(organization_id=self.get_membership().organization_id).order_by("name")

    def owners_with_balance(self):
        from apps.payments.api import open_customer_documents

        sales, orders = open_customer_documents(self.get_membership())
        return Q(pk__in=sales.values("customer_id")) | Q(pk__in=orders.values("customer_id"))

    def balances_for(self, ids):
        from apps.payments.api import scoped_orders, scoped_sales

        membership = self.get_membership()
        return customer_balances(scoped_sales(membership), ids, scoped_orders(membership))

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        from apps.payments.api import CustomerPaymentSerializer, open_customer_documents, scoped_orders, scoped_sales
        from apps.payments.models import CustomerPayment

        customer = self.get_object()
        membership = self.get_membership()
        sales, orders = open_customer_documents(membership, customer)
        documents = [
            {
                "id": str(s.pk),
                "kind": "sale",
                "number": s.number,
                "date": s.posted_at.date().isoformat(),
                "sort": s.posted_at,
                "currency": s.currency,
                "total": str(s.total),
                "paid": str(s.paid_amount),
                "due": str(s.total - s.paid_amount),
            }
            for s in sales
        ]
        documents += [
            {
                "id": str(o.pk),
                "kind": "order",
                "number": o.number,
                "date": o.created_at.date().isoformat(),
                "sort": o.created_at,
                "currency": o.currency,
                "total": str(o.total),
                "paid": str(o.paid_amount),
                "due": str(o.total - o.paid_amount),
                "status": f"{o.title} · {o.status_label}",
            }
            for o in orders
        ]
        documents.sort(key=lambda d: d.pop("sort"))
        payments = (
            CustomerPayment.objects.filter(
                Q(allocations__sale__in=scoped_sales(membership)) | Q(allocations__custom_order__in=scoped_orders(membership)),
                customer=customer,
            )
            .distinct()
            .select_related("created_by", "reversed_by")
            .prefetch_related("allocations__sale", "allocations__custom_order")
            .order_by("-received_at")[:25]
        )
        return Response(
            {
                "balances": self.balances_for([customer.pk]).get(customer.pk, {}),
                "open_documents": documents,
                "payments": CustomerPaymentSerializer(payments, many=True).data,
            }
        )


class SupplierViewSet(BalanceMixin, ScopedViewSet):
    serializer_class = SupplierSerializer
    read_permission = "suppliers.view"
    create_permission = "suppliers.create"
    update_permission = "suppliers.manage"
    extra_action_permissions = {"statement": "purchases.view"}
    balance_permission = "purchases.view"
    search_fields = ("name", "phone", "email", "location")

    def get_queryset(self):
        return Supplier.objects.filter(organization_id=self.get_membership().organization_id).order_by("name")

    def open_documents(self):
        from apps.payments.api import scoped_purchases

        return scoped_purchases(self.get_membership()).exclude(status="cancelled").filter(paid_amount__lt=F("total"))

    def owners_with_balance(self):
        return Q(pk__in=self.open_documents().values("supplier_id"))

    def balances_for(self, ids):
        from apps.payments.api import scoped_purchases

        return supplier_balances(scoped_purchases(self.get_membership()), ids)

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        from apps.payments.api import SupplierPaymentSerializer, scoped_purchases
        from apps.payments.models import SupplierPayment

        supplier = self.get_object()
        open_purchases = self.open_documents().filter(supplier=supplier).order_by("purchase_date", "created_at")
        payments = (
            SupplierPayment.objects.filter(supplier=supplier, allocations__purchase__in=scoped_purchases(self.get_membership()))
            .distinct()
            .select_related("created_by", "reversed_by")
            .prefetch_related("allocations__purchase")
            .order_by("-paid_on", "-created_at")[:25]
        )
        return Response(
            {
                "balances": self.balances_for([supplier.pk]).get(supplier.pk, {}),
                "open_documents": [
                    {
                        "id": str(p.pk),
                        "number": p.number,
                        "date": p.purchase_date.isoformat(),
                        "currency": p.currency,
                        "total": str(p.total),
                        "paid": str(p.paid_amount),
                        "due": str(p.total - p.paid_amount),
                        "status": p.get_status_display(),
                    }
                    for p in open_purchases
                ],
                "payments": SupplierPaymentSerializer(payments, many=True).data,
            }
        )


class CategoryViewSet(ScopedViewSet):
    serializer_class = CategorySerializer
    read_permission = "catalog.view"
    create_permission = "catalog.create"
    update_permission = "catalog.manage"
    search_fields = ("name",)

    def get_queryset(self):
        membership = self.get_membership()
        sections = allowed_section_ids(membership)
        return (
            Category.objects.filter(organization_id=membership.organization_id)
            .filter(Q(section__isnull=True) | Q(section_id__in=sections))
            .order_by("name")
        )


class ProductViewSet(ScopedViewSet):
    serializer_class = ProductSerializer
    read_permission = "catalog.view"
    create_permission = "catalog.create"
    update_permission = "catalog.manage"
    search_fields = ("name", "sku")

    def get_queryset(self):
        from django.db.models import OuterRef, Subquery

        from apps.files.models import Attachment

        image = Attachment.objects.filter(purpose="product_image", owner_id=OuterRef("pk")).order_by("-created_at").values("id")[:1]
        return (
            scope_queryset(Product.objects.all(), self.get_membership())
            .select_related("section", "category")
            .prefetch_related("variants")
            .annotate(image_id=Subquery(image))
        )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if serializer.instance.tracks_stock:
            ensure_default_variant(serializer.instance)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        product = serializer.instance
        if product.tracks_stock and not product.variants.exists():
            ensure_default_variant(product)

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
        return ProductVariant.objects.filter(
            product__organization_id=membership.organization_id, product__section_id__in=allowed_section_ids(membership)
        ).select_related("product")

    def get_create_kwargs(self):
        return {}

    def perform_create(self, serializer):
        product = serializer.validated_data["product"]
        membership = self.get_membership()
        if product.organization_id != membership.organization_id or product.section_id not in allowed_section_ids(membership):
            raise NotFound()
        super().perform_create(serializer)
        # The first real option replaces the placeholder default variant, if it never held stock.
        default = product.variants.filter(code="default", active=True).exclude(pk=serializer.instance.pk).first()
        if default and not default.stock_movements.exists():
            default.active = False
            default.save(update_fields=["active"])
