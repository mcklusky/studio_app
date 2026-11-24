from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import PasswordResetForm
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.identity.scope import allowed_branch_ids, allowed_section_ids, resolve_membership
from apps.organizations.models import Branch, BusinessSection


def current_user_payload(user):
    memberships = user.organization_memberships.filter(active=True, organization__active=True).select_related("organization", "role")
    return {
        "id": str(user.pk),
        "username": user.get_username(),
        "display_name": user.get_full_name() or user.get_username(),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "last_login": user.last_login,
        "organizations": [{"id": str(m.organization_id), "name": m.organization.name, "role": m.role.name} for m in memberships],
    }


@ensure_csrf_cookie
def csrf_cookie(request):
    return JsonResponse({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_active:
            raise ValidationError("Invalid username or password.")
        login(request, user)
        from apps.identity.staff import record_login

        record_login(request, user)
        return Response(current_user_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response(status=204)


@method_decorator(csrf_protect, name="dispatch")
class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset"

    def post(self, request):
        form = PasswordResetForm({"email": str(request.data.get("email", "")).strip()})
        if form.is_valid():
            from urllib.parse import urlparse

            from django.conf import settings

            public_url = getattr(settings, "PUBLIC_APP_URL", "")
            domain = urlparse(public_url).netloc
            if domain:
                form.save(
                    request=request,
                    domain_override=domain,
                    use_https=public_url.startswith("https://"),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                )
        return Response({"detail": "If an account matches that email, password reset instructions will be sent."})


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(current_user_payload(request.user))

    def patch(self, request):
        """Edit your own name and email. Username, role and access are changed by an administrator."""
        user = request.user
        errors, changes = {}, {}
        for field, limit in (("first_name", 150), ("last_name", 150), ("email", 254)):
            if field not in request.data:
                continue
            value = request.data.get(field)
            if not isinstance(value, str):
                errors[field] = ["Enter text."]
                continue
            value = value.strip()
            if len(value) > limit:
                errors[field] = [f"Keep this under {limit} characters."]
            changes[field] = value
        if changes.get("email"):
            try:
                validate_email(changes["email"])
            except DjangoValidationError:
                errors["email"] = ["Enter a valid email address."]
        if errors:
            raise ValidationError(errors)
        if changes:
            for field, value in changes.items():
                setattr(user, field, value)
            user.save(update_fields=list(changes))
            for membership in user.organization_memberships.filter(active=True).select_related("organization"):
                record_event(
                    organization=membership.organization,
                    action="user.profile_updated",
                    entity=user,
                    request=request,
                    summary={"fields": sorted(changes)},
                )
        return Response(current_user_payload(user))


class OrganizationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        organization = membership.organization
        return Response(
            {
                "id": str(organization.pk),
                "name": organization.name,
                "base_currency": organization.base_currency,
                "timezone": organization.timezone,
                "role": membership.role.name,
                "role_code": membership.role.code,
                "permissions": sorted(membership.role.permissions.values_list("code", flat=True)),
                "section_ids": [str(value) for value in allowed_section_ids(membership)],
                "branch_ids": [str(value) for value in allowed_branch_ids(membership)],
            }
        )


class SectionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        sections = BusinessSection.objects.filter(organization=membership.organization, active=True)
        if not membership.all_sections:
            sections = sections.filter(id__in=allowed_section_ids(membership))
        return Response([{"id": str(s.pk), "name": s.name, "code": s.code} for s in sections])


class BranchListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        branches = Branch.objects.filter(organization=membership.organization, active=True)
        if not membership.all_branches:
            branches = branches.filter(id__in=allowed_branch_ids(membership))
        return Response(
            [
                {"id": str(b.pk), "name": b.name, "code": b.code, "timezone": b.timezone or membership.organization.timezone}
                for b in branches
            ]
        )
