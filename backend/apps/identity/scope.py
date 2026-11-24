from django.core.exceptions import PermissionDenied
from django.db.models import Q
from rest_framework.exceptions import NotFound

from apps.identity.models import Membership


def resolve_membership(user, organization_id=None):
    """Resolve an active membership; an optional org ID is only a selector, never authority."""
    if not getattr(user, "is_authenticated", False):
        raise PermissionDenied("Authentication is required.")
    memberships = Membership.objects.filter(user=user, active=True, organization__active=True).select_related("organization", "role")
    if organization_id:
        membership = memberships.filter(organization_id=organization_id).first()
    else:
        membership = memberships.order_by("created_at").first() if memberships.count() == 1 else None
    if membership is None:
        raise NotFound("Organization membership was not found.")
    return membership


def allowed_section_ids(membership):
    if not membership.active:
        return []
    if membership.all_sections:
        from apps.organizations.models import BusinessSection
        return list(BusinessSection.objects.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))
    return list(membership.sections.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))


def allowed_branch_ids(membership):
    if not membership.active:
        return []
    if membership.all_branches:
        from apps.organizations.models import Branch
        return list(Branch.objects.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))
    return list(membership.branches.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))


def has_permission(membership, permission_code):
    return bool(membership and membership.active and membership.role.organization_id == membership.organization_id
                and membership.role.permissions.filter(code=permission_code).exists())


def require_permission(membership, permission_code):
    if not has_permission(membership, permission_code):
        raise PermissionDenied("You do not have permission to perform this action.")


def scope_queryset(queryset, membership, *, section_field="section_id", branch_field="branch_id"):
    """Apply organization and optional section/branch boundaries to a business queryset."""
    if not membership or not membership.active:
        return queryset.none()
    filters = {"organization_id": membership.organization_id}
    queryset = queryset.filter(**filters)
    model_fields = {field.name for field in queryset.model._meta.get_fields()}
    section_name = section_field.removesuffix("_id")
    branch_name = branch_field.removesuffix("_id")
    if section_name in model_fields:
        allowed_sections = allowed_section_ids(membership)
        queryset = queryset.filter(**{section_field + "__in": allowed_sections}) if allowed_sections else queryset.none()
    if branch_name in model_fields:
        allowed_branches = allowed_branch_ids(membership)
        queryset = queryset.filter(Q(**{branch_field: None}) | Q(**{branch_field + "__in": allowed_branches})) if allowed_branches else queryset.filter(**{branch_field: None})
    return queryset
