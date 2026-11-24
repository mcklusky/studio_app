import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.organizations.models import BusinessSection, Organization


class Customer(models.Model):
    class Type(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        BUSINESS = "business", "Business"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="customers")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=240, blank=True)
    customer_type = models.CharField(max_length=20, choices=Type.choices, default=Type.INDIVIDUAL)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["organization", "name"], name="customer_org_name_idx")]

    def __str__(self):
        return self.name


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="suppliers")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    location = models.CharField(max_length=240, blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        indexes = [models.Index(fields=["organization", "name"], name="supplier_org_name_idx")]

    def __str__(self):
        return self.name


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="categories")
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, null=True, blank=True, related_name="categories")
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], condition=Q(section__isnull=True), name="uniq_shared_category_name_org"),
            models.UniqueConstraint(fields=["organization", "section", "name"], condition=Q(section__isnull=False), name="uniq_section_category_name_org"),
        ]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Kind(models.TextChoices):
        PRODUCT = "product", "Product"
        SERVICE = "service", "Service"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="products")
    section = models.ForeignKey(BusinessSection, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=160)
    sku = models.CharField(max_length=80, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PRODUCT)
    tracks_stock = models.BooleanField(default=True)
    buying_price_base = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    selling_price_base = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    minimum_stock = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [models.UniqueConstraint(fields=["organization", "sku"], condition=~Q(sku=""), name="uniq_product_sku_per_org")]
        indexes = [models.Index(fields=["organization", "section", "status"], name="product_org_section_status_idx")]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.section_id and self.organization_id and self.section.organization_id != self.organization_id:
            raise ValidationError({"section": "Section must belong to the product organization."})
        if self.category_id and self.organization_id and self.category.organization_id != self.organization_id:
            raise ValidationError({"category": "Category must belong to the product organization."})
        if self.category_id and self.category.section_id and self.category.section_id != self.section_id:
            raise ValidationError({"category": "Category must match the product section."})
        if self.kind == self.Kind.SERVICE and self.tracks_stock:
            raise ValidationError({"tracks_stock": "Services cannot track inventory stock."})

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    code = models.CharField(max_length=80, default="default")
    size = models.CharField(max_length=40, blank=True)
    color = models.CharField(max_length=60, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["product", "code"], name="uniq_variant_code_per_product")]

    def __str__(self):
        return f"{self.product.name} · {self.code}"
