from rest_framework import serializers

from apps.catalog.models import Category, Customer, Product, ProductVariant, Supplier
from apps.identity.scope import allowed_section_ids


class CustomerSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Customer
        fields = ("id", "organization_id", "name", "phone", "email", "address", "customer_type", "notes", "active", "created_at", "updated_at")
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
        if section and (section.organization_id != organization_id or section.id not in allowed_section_ids(self.context["request"].membership)):
            raise serializers.ValidationError({"section": "Choose a section available in your organization."})
        return attrs


class ProductSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Product
        fields = ("id", "organization_id", "section", "category", "name", "sku", "kind", "tracks_stock", "buying_price_base", "selling_price_base", "minimum_stock", "status", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs):
        membership = self.context["request"].membership
        section = attrs.get("section", getattr(self.instance, "section", None))
        category = attrs.get("category", getattr(self.instance, "category", None))
        kind = attrs.get("kind", getattr(self.instance, "kind", Product.Kind.PRODUCT))
        tracks_stock = attrs.get("tracks_stock", getattr(self.instance, "tracks_stock", True))
        if not section or section.organization_id != membership.organization_id or section.id not in allowed_section_ids(membership):
            raise serializers.ValidationError({"section": "Choose a section available in your organization."})
        if category and (category.organization_id != membership.organization_id or (category.section_id and category.section_id != section.id)):
            raise serializers.ValidationError({"category": "Choose a category for this organization and section."})
        if kind == Product.Kind.SERVICE and tracks_stock:
            raise serializers.ValidationError({"tracks_stock": "Services cannot track inventory stock."})
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

