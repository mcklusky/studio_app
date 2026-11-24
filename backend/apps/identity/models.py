import uuid

from django.conf import settings
from django.db import models

from apps.organizations.models import Branch, BusinessSection, Organization


class AccessPermission(models.Model):
    """Application-level permission code; Django model permissions are not business grants."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=200)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=100)
    code = models.SlugField(max_length=40)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(AccessPermission, blank=True, related_name="roles")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["organization", "code"], name="uniq_role_code_per_org")]

    def __str__(self):
        return f"{self.organization}: {self.name}"


class Membership(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organization_memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    active = models.BooleanField(default=True)
    all_sections = models.BooleanField(default=False)
    all_branches = models.BooleanField(default=False)
    sections = models.ManyToManyField(BusinessSection, blank=True, related_name="memberships")
    branches = models.ManyToManyField(Branch, blank=True, related_name="memberships")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "organization"], name="uniq_membership_user_org")]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.role_id and self.organization_id and self.role.organization_id != self.organization_id:
            raise ValidationError({"role": "Role must belong to the same organization as this membership."})
        if self.pk:
            if self.sections.exclude(organization_id=self.organization_id).exists():
                raise ValidationError({"sections": "Section scope must belong to the membership organization."})
            if self.branches.exclude(organization_id=self.organization_id).exists():
                raise ValidationError({"branches": "Branch scope must belong to the membership organization."})

    def __str__(self):
        return f"{self.user} @ {self.organization}"
