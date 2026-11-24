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


SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def focus_on_view(membership, request):
    """Apply the top-bar section/branch selector (X-Section-ID / X-Branch-ID) to reads only.

    The focus can only narrow what the membership already allows: a value outside the
    person's scope is ignored, never widened. Writes always use the full scope, so a form
    can still record work for any section the person is allowed.
    """
    if request.method in SAFE_METHODS:
        membership.focus_section = (request.headers.get("X-Section-ID") or "").strip() or None
        membership.focus_branch = (request.headers.get("X-Branch-ID") or "").strip() or None
    return membership


def _focus(ids, chosen):
    if chosen:
        picked = [value for value in ids if str(value) == chosen]
        if picked:
            return picked
    return ids


def allowed_section_ids(membership, *, full=False):
    """Sections the person may see; narrowed to the top-bar focus on reads unless full=True."""
    if not membership.active:
        return []
    if membership.all_sections:
        from apps.organizations.models import BusinessSection

        ids = list(BusinessSection.objects.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))
    else:
        ids = list(membership.sections.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))
    return ids if full else _focus(ids, getattr(membership, "focus_section", None))


def allowed_branch_ids(membership, *, full=False):
    """Branches the person may see; narrowed to the top-bar focus on reads unless full=True."""
    if not membership.active:
        return []
    if membership.all_branches:
        from apps.organizations.models import Branch

        ids = list(Branch.objects.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))
    else:
        ids = list(membership.branches.filter(organization_id=membership.organization_id, active=True).values_list("id", flat=True))
    return ids if full else _focus(ids, getattr(membership, "focus_branch", None))


def has_permission(membership, permission_code):
    return bool(
        membership
        and membership.active
        and membership.role.organization_id == membership.organization_id
        and membership.role.permissions.filter(code=permission_code).exists()
    )


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
        queryset = (
            queryset.filter(Q(**{branch_field: None}) | Q(**{branch_field + "__in": allowed_branches}))
            if allowed_branches
            else queryset.filter(**{branch_field: None})
        )
    return queryset
