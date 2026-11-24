import uuid

from django.db import models


class Organization(models.Model):
    class Currency(models.TextChoices):
        USD = "USD", "US Dollar"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    base_currency = models.CharField(max_length=3, choices=Currency.choices, default=Currency.USD)
    timezone = models.CharField(max_length=64, default="Africa/Monrovia")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BusinessSection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="sections")
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=40)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="uniq_section_code_per_org")]

    def __str__(self):
        return f"{self.organization}: {self.name}"


class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=40)
    timezone = models.CharField(max_length=64, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="uniq_branch_code_per_org")]

    def __str__(self):
        return f"{self.organization}: {self.name}"
