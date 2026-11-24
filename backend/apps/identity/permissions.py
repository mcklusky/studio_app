from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from apps.identity.scope import focus_on_view, has_permission, resolve_membership


class HasBusinessPermission(BasePermission):
    """Views must declare permission_code; missing configuration is denied."""

    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        permission_resolver = getattr(view, "get_required_permission", None)
        permission_code = permission_resolver(request) if permission_resolver else getattr(view, "permission_code", None)
        if not permission_code or not request.user.is_authenticated:
            return False
        org_id = request.headers.get("X-Organization-ID")
        try:
            membership = resolve_membership(request.user, org_id)
        except NotFound:
            return False
        request.membership = focus_on_view(membership, request)
        return has_permission(membership, permission_code)
