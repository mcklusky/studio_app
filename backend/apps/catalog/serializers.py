from rest_framework import serializers

from apps.catalog.models import Category, Customer, Product, ProductVariant, Supplier
from apps.identity.scope import allowed_section_ids, has_permission


class CustomerSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "organization_id",
            "name",
            "phone",
            "email",
            "address",
            "customer_type",
            "notes",
            "active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class SupplierSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Supplier
        fields = ("id", "organization_id", "name", "phone", "email", "location", "notes", "active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class CategorySerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "organization_id", "section", "name", "active", "created_at")
        read_only_fields = ("id", "created_at")

    def validate(self, attrs):
        section = attrs.get("section", getattr(self.instance, "section", None))
        organization_id = self.context["request"].membership.organization_id
        if section and (
            section.organization_id != organization_id or section.id not in allowed_section_ids(self.context["request"].membership)
        ):
            raise serializers.ValidationError({"section": "Choose a section available in your organization."})
        return attrs


class VariantSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ("id", "code", "size", "color", "active")


class ProductSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    variants = VariantSummarySerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "organization_id",
            "section",
            "section_name",
            "category",
            "category_name",
            "name",
            "sku",
            "kind",
            "tracks_stock",
            "buying_price_base",
            "selling_price_base",
            "minimum_stock",
            "status",
            "show_online",
            "public_description",
            "variants",
            "image_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def get_image_url(self, product):
        image_id = getattr(product, "image_id", None)
        if image_id is None and not hasattr(product, "image_id"):
            from apps.files.models import Attachment

            image_id = (
                Attachment.objects.filter(purpose="product_image", owner_id=product.pk)
                .order_by("-created_at")
                .values_list("id", flat=True)
                .first()
            )
        return f"/api/v1/attachments/{image_id}/file/" if image_id else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if request is not None and not has_permission(getattr(request, "membership", None), "inventory.costs"):
            data.pop("buying_price_base", None)
        return data

    def validate(self, attrs):
        membership = self.context["request"].membership
        section = attrs.get("section", getattr(self.instance, "section", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", Product.Kind.PRODUCT))
        tracks_stock = attrs.get("tracks_stock", getattr(self.instance, "tracks_stock", True))
        if not section or section.organization_id != membership.organization_id or section.id not in allowed_section_ids(membership):
            raise serializers.ValidationError({"section": "Choose a section available in your organization."})
        if category and (
            category.organization_id != membership.organization_id or (category.section_id and category.section_id != section.id)
        ):
            raise serializers.ValidationError({"category": "Choose a category for this organization and section."})
        if kind == Product.Kind.SERVICE and tracks_stock:
            raise serializers.ValidationError({"tracks_stock": "Services cannot track inventory stock."})
        if self.instance and not tracks_stock and self.instance.tracks_stock:
            from apps.inventory.models import StockBalance

            if StockBalance.objects.filter(variant__product=self.instance, quantity__gt=0).exists():
                raise serializers.ValidationError({"tracks_stock": "Adjust stock to zero before turning off stock tracking."})
        if self.instance and section != self.instance.section and self.instance.variants.filter(stock_movements__isnull=False).exists():
            raise serializers.ValidationError({"section": "This product has stock history and cannot move to another section."})
        return attrs


class ProductVariantSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    product_id = serializers.UUIDField(source="product.id", read_only=True)

    class Meta:
        model = ProductVariant
        fields = ("id", "product", "product_id", "code", "size", "color", "active", "created_at")
        read_only_fields = ("id", "product_id", "created_at")

    def validate_product(self, product):
        membership = self.context["request"].membership
        if product.organization_id != membership.organization_id or product.section_id not in allowed_section_ids(membership):
            raise serializers.ValidationError("Choose a product in an accessible section.")
        return product
