"""Staff accounts, roles and access scope (REQ-002, REQ-031, US-06).

Rules:
* Every person has their own account; usernames are unique across the system.
* Accounts are never deleted. Deactivating keeps every record they made
  attributed to them; it blocks access to this organization at once.
* The organization must always keep at least one active owner/admin, and only
  an owner/admin can make someone else an owner/admin.
* You cannot deactivate or demote yourself (ask another admin).
* Passwords follow Django's validators. A temporary password is shown to the
  admin once; resetting it signs the person out everywhere.
* Built-in roles are read-only (they are kept in sync from access.py); custom
  roles can be created and edited by holders of roles.manage.
"""

import secrets
import string

from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils.text import slugify
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services import record_event
from apps.common.exceptions import Conflict
from apps.identity.access import PERMISSIONS
from apps.identity.models import AccessPermission, Membership, Role
from apps.identity.permissions import HasBusinessPermission
from apps.organizations.models import Branch, BusinessSection

User = get_user_model()
OWNER_ROLE = "owner-admin"

# Groups for showing the permission catalog to people (order matters).
PERMISSION_GROUPS = [
    ("Sales & customers", ("sales.", "customers.")),
    ("Department orders", ("orders.",)),
    ("Products & stock", ("catalog.", "inventory.")),
    ("Suppliers & purchases", ("suppliers.", "purchases.", "payables.")),
    ("Expenses", ("expenses.",)),
    ("Money & reports", ("dashboard.", "reports.", "fx.")),
    ("Administration", ("organization.", "staff.", "roles.", "audit.")),
]


def temporary_password():
    """Readable 12-character password: letters and digits, no look-alikes."""
    alphabet = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isdigit() for c in value) and any(c.isupper() for c in value) and any(c.islower() for c in value):
            return value


def _check_password(password, user=None):
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)}) from None


def person(user):
    return user.get_full_name() or user.get_username()


def _active_owner_count(organization, exclude=None):
    queryset = Membership.objects.filter(organization=organization, active=True, role__code=OWNER_ROLE, user__is_active=True)
    if exclude is not None:
        queryset = queryset.exclude(pk=exclude.pk)
    return queryset.count()


def _sync_user_active(user):
    """A user with no active membership anywhere cannot sign in (their sessions stop working too)."""
    should_be_active = user.organization_memberships.filter(active=True, organization__active=True).exists()
    if user.is_active != should_be_active:
        user.is_active = should_be_active
        user.save(update_fields=["is_active"])


# ---------- serializers ----------


class StaffSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.pk", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)
    email = serializers.CharField(source="user.email", read_only=True)
    name = serializers.SerializerMethodField()
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    section_ids = serializers.SerializerMethodField()
    branch_ids = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(source="user.last_login", read_only=True)
    is_you = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = (
            "id",
            "user_id",
            "username",
            "first_name",
            "last_name",
            "email",
            "name",
            "role",
            "role_code",
            "role_name",
            "all_sections",
            "section_ids",
            "all_branches",
            "branch_ids",
            "active",
            "last_login",
            "created_at",
            "is_you",
        )

    def get_name(self, membership):
        return person(membership.user)

    def get_section_ids(self, membership):
        return [str(s.pk) for s in membership.sections.all()]

    def get_branch_ids(self, membership):
        return [str(b.pk) for b in membership.branches.all()]

    def get_is_you(self, membership):
        request = self.context.get("request")
        return bool(request and membership.user_id == request.user.pk)


class StaffInput(serializers.Serializer):
    username = serializers.RegexField(
        r"^[\w.@+-]+$", max_length=150, required=False, error_messages={"invalid": "Use letters, numbers and . @ + - _ only (no spaces)."}
    )
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), required=False)
    all_sections = serializers.BooleanField(required=False)
    sections = serializers.PrimaryKeyRelatedField(queryset=BusinessSection.objects.all(), many=True, required=False)
    all_branches = serializers.BooleanField(required=False)
    branches = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all(), many=True, required=False)
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, trim_whitespace=False)


# ---------- views ----------


class StaffViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    serializer_class = StaffSerializer
    PERMISSIONS = {
        "list": "staff.manage",
        "retrieve": "staff.manage",
        "create": "staff.manage",
        "partial_update": "staff.manage",
        "deactivate": "staff.manage",
        "reactivate": "staff.manage",
        "reset_password": "staff.manage",
    }

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_queryset(self):
        queryset = (
            Membership.objects.filter(organization_id=self.request.membership.organization_id)
            .select_related("user", "role")
            .prefetch_related("sections", "branches")
            .order_by("-active", "user__first_name", "user__username")
        )
        params = self.request.query_params
        if params.get("status") in ("active", "inactive"):
            queryset = queryset.filter(active=params["status"] == "active")
        if params.get("search"):
            term = params["search"].strip()
            queryset = queryset.filter(
                Q(user__username__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__email__icontains=term)
            )
        return queryset

    def _out(self, membership, status=200, extra=None):
        membership = self.get_queryset().get(pk=membership.pk)
        data = StaffSerializer(membership, context=self.get_serializer_context()).data
        return Response({**data, **(extra or {})}, status=status)

    def _validated(self, request, membership=None):
        serializer = StaffInput(data=request.data, partial=membership is not None)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        org = request.membership.organization
        if "role" in data:
            if data["role"].organization_id != org.pk:
                raise ValidationError({"role": ["Choose a role from this organization."]})
            if data["role"].code == OWNER_ROLE and request.membership.role.code != OWNER_ROLE:
                raise PermissionDenied("Only an owner/admin can give someone the owner/admin role.")
        for field, label in (("sections", "section"), ("branches", "branch")):
            if any(item.organization_id != org.pk for item in data.get(field, [])):
                raise ValidationError({field: [f"Choose a {label} from this organization."]})
        return data

    @staticmethod
    def _scope_ok(all_flag, items, label):
        if not all_flag and not items:
            raise ValidationError({f"{label}s": [f"Choose at least one {label}, or give access to all {label}s."]})

    @transaction.atomic
    def create(self, request):
        data = self._validated(request)
        missing = {f: ["This field is required."] for f in ("username", "role") if not data.get(f)}
        if not (data.get("first_name") or "").strip():
            missing["first_name"] = ["Enter the person's first name."]
        if missing:
            raise ValidationError(missing)
        if User.objects.filter(username__iexact=data["username"]).exists():
            raise ValidationError({"username": ["That username is already taken. Try adding a number or initial."]})
        all_sections, all_branches = data.get("all_sections", False), data.get("all_branches", True)
        self._scope_ok(all_sections, data.get("sections"), "section")
        self._scope_ok(all_branches, data.get("branches"), "branch")
        user = User(
            username=data["username"],
            first_name=data.get("first_name", "").strip(),
            last_name=data.get("last_name", "").strip(),
            email=data.get("email", "").strip(),
        )
        password = data.get("password") or ""
        generated = not password
        password = password or temporary_password()
        _check_password(password, user)
        user.set_password(password)
        user.save()
        membership = Membership.objects.create(
            user=user, organization=request.membership.organization, role=data["role"], all_sections=all_sections, all_branches=all_branches
        )
        membership.sections.set([] if all_sections else data.get("sections", []))
        membership.branches.set([] if all_branches else data.get("branches", []))
        record_event(
            organization=membership.organization,
            action="staff.created",
            entity=membership,
            request=request,
            summary={
                "username": user.username,
                "role": data["role"].code,
                "all_sections": all_sections,
                "sections": [s.code for s in data.get("sections", [])],
            },
        )
        return self._out(membership, status=201, extra={"temporary_password": password} if generated else None)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        membership = self.get_object()
        data = self._validated(request, membership)
        if "username" in data or "password" in data:
            raise ValidationError({"username": ["Usernames cannot be changed; use Reset password for passwords."]})
        changes = {}
        user = membership.user
        for field in ("first_name", "last_name", "email"):
            if field in data and data[field].strip() != getattr(user, field):
                setattr(user, field, data[field].strip())
                changes[field] = "[changed]" if field == "email" else data[field].strip()
        if "first_name" in data and not data["first_name"].strip():
            raise ValidationError({"first_name": ["Enter the person's first name."]})
        user.save()
        if "role" in data and data["role"].pk != membership.role_id:
            if membership.user_id == request.user.pk:
                raise Conflict("You cannot change your own role. Ask another owner/admin.")
            if (
                membership.role.code == OWNER_ROLE
                and membership.active
                and not _active_owner_count(membership.organization, exclude=membership)
            ):
                raise Conflict("This is the only active owner/admin. Make someone else an owner/admin first.")
            changes["role"] = [membership.role.code, data["role"].code]
            membership.role = data["role"]
        all_sections = data.get("all_sections", membership.all_sections)
        all_branches = data.get("all_branches", membership.all_branches)
        sections = data.get("sections", list(membership.sections.all()))
        branches = data.get("branches", list(membership.branches.all()))
        self._scope_ok(all_sections, sections, "section")
        self._scope_ok(all_branches, branches, "branch")
        if any(k in data for k in ("all_sections", "sections")):
            changes["sections"] = "all" if all_sections else sorted(s.code for s in sections)
        if any(k in data for k in ("all_branches", "branches")):
            changes["branches"] = "all" if all_branches else sorted(b.code for b in branches)
        membership.all_sections, membership.all_branches = all_sections, all_branches
        membership.save()
        membership.sections.set([] if all_sections else sections)
        membership.branches.set([] if all_branches else branches)
        if changes:
            record_event(
                organization=membership.organization,
                action="staff.updated",
                entity=membership,
                request=request,
                summary={"username": user.username, "changes": changes},
            )
        return self._out(membership)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def deactivate(self, request, pk=None):
        membership = Membership.objects.select_for_update().get(pk=self.get_object().pk)
        if membership.user_id == request.user.pk:
            raise Conflict("You cannot deactivate your own account.")
        if not membership.active:
            raise Conflict("This account is already deactivated.")
        if membership.role.code == OWNER_ROLE and not _active_owner_count(membership.organization, exclude=membership):
            raise Conflict("This is the only active owner/admin and cannot be deactivated.")
        membership.active = False
        membership.save(update_fields=["active", "updated_at"])
        _sync_user_active(membership.user)
        record_event(
            organization=membership.organization,
            action="staff.deactivated",
            entity=membership,
            request=request,
            summary={"username": membership.user.username, "reason": str(request.data.get("reason", ""))[:240]},
        )
        return self._out(membership)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def reactivate(self, request, pk=None):
        membership = self.get_object()
        if membership.active:
            raise Conflict("This account is already active.")
        membership.active = True
        membership.save(update_fields=["active", "updated_at"])
        _sync_user_active(membership.user)
        record_event(
            organization=membership.organization,
            action="staff.reactivated",
            entity=membership,
            request=request,
            summary={"username": membership.user.username},
        )
        return self._out(membership)

    @action(detail=True, methods=["post"], url_path="reset-password")
    @transaction.atomic
    def reset_password(self, request, pk=None):
        membership = self.get_object()
        user = membership.user
        if user.pk == request.user.pk:
            raise Conflict("Use Change password for your own account.")
        if user.organization_memberships.exclude(organization_id=membership.organization_id).filter(active=True).exists():
            raise Conflict("This person also works in another organization; ask them to reset their own password.")
        password = temporary_password()
        user.set_password(password)  # changing the hash signs them out of every session
        user.save(update_fields=["password"])
        record_event(
            organization=membership.organization,
            action="staff.password_reset",
            entity=membership,
            request=request,
            summary={"username": user.username},
        )
        return self._out(membership, extra={"temporary_password": password})


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ("id", "code", "name", "is_system", "permissions", "member_count")

    def get_permissions(self, role):
        return sorted(p.code for p in role.permissions.all())

    def get_member_count(self, role):
        return sum(1 for m in role.memberships.all() if m.active)


class RoleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Roles and the permission catalog. Built-in roles are read-only."""

    permission_classes = [IsAuthenticated, HasBusinessPermission]
    serializer_class = RoleSerializer
    PERMISSIONS = {
        "list": "staff.manage",
        "retrieve": "staff.manage",
        "catalog": "staff.manage",
        "create": "roles.manage",
        "partial_update": "roles.manage",
    }

    def get_required_permission(self, _request):
        return self.PERMISSIONS.get(getattr(self, "action", None))

    def get_queryset(self):
        return (
            Role.objects.filter(organization_id=self.request.membership.organization_id)
            .prefetch_related("permissions", "memberships")
            .order_by("-is_system", "name")
        )

    @action(detail=False, methods=["get"])
    def catalog(self, request):
        groups = []
        for title, prefixes in PERMISSION_GROUPS:
            codes = [c for c in PERMISSIONS if c.startswith(prefixes)]
            groups.append({"title": title, "permissions": [{"code": c, "description": PERMISSIONS[c]} for c in codes]})
        return Response(groups)

    def _permissions(self, request):
        codes = request.data.get("permissions")
        if not isinstance(codes, list) or not codes:
            raise ValidationError({"permissions": ["Choose at least one permission."]})
        unknown = sorted(set(codes) - set(PERMISSIONS))
        if unknown:
            raise ValidationError({"permissions": [f"Unknown permission: {', '.join(unknown)}."]})
        if request.membership.role.code != OWNER_ROLE and not set(codes) <= set(
            request.membership.role.permissions.values_list("code", flat=True)
        ):
            raise PermissionDenied("You can only grant permissions you hold yourself.")
        return AccessPermission.objects.filter(code__in=codes)

    @transaction.atomic
    def create(self, request):
        name = str(request.data.get("name", "")).strip()[:100]
        if not name:
            raise ValidationError({"name": ["Name the role, e.g. Senior cashier."]})
        code = slugify(name)[:40] or "role"
        org = request.membership.organization
        if Role.objects.filter(organization=org).filter(Q(code=code) | Q(name__iexact=name)).exists():
            raise ValidationError({"name": ["A role with this name already exists."]})
        role = Role.objects.create(organization=org, name=name, code=code, is_system=False)
        role.permissions.set(self._permissions(request))
        record_event(
            organization=org,
            action="role.created",
            entity=role,
            request=request,
            summary={"name": name, "permissions": sorted(role.permissions.values_list("code", flat=True))},
        )
        return Response(RoleSerializer(self.get_queryset().get(pk=role.pk)).data, status=201)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        role = self.get_object()
        if role.is_system:
            raise Conflict("Built-in roles cannot be edited. Create a custom role instead.")
        before = set(role.permissions.values_list("code", flat=True))
        if "name" in request.data:
            name = str(request.data["name"]).strip()[:100]
            if not name:
                raise ValidationError({"name": ["Name the role."]})
            if Role.objects.filter(organization=role.organization, name__iexact=name).exclude(pk=role.pk).exists():
                raise ValidationError({"name": ["A role with this name already exists."]})
            role.name = name
            role.save(update_fields=["name"])
        if "permissions" in request.data:
            role.permissions.set(self._permissions(request))
        after = set(role.permissions.values_list("code", flat=True))
        record_event(
            organization=role.organization,
            action="role.updated",
            entity=role,
            request=request,
            summary={"name": role.name, "added": sorted(after - before), "removed": sorted(before - after)},
        )
        return Response(RoleSerializer(self.get_queryset().get(pk=role.pk)).data)


class ChangePasswordView(APIView):
    """Signed-in users change their own password (current password required)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if not user.check_password(str(request.data.get("current_password", ""))):
            raise ValidationError({"current_password": ["That is not your current password."]})
        new = str(request.data.get("new_password", ""))
        _check_password(new, user)
        user.set_password(new)
        user.save(update_fields=["password"])
        update_session_auth_hash(request, user)  # stay signed in here; other sessions end
        for membership in user.organization_memberships.filter(active=True).select_related("organization"):
            record_event(
                organization=membership.organization,
                action="auth.password_changed",
                entity=membership,
                request=request,
                summary={"username": user.username},
            )
        return Response({"detail": "Password changed."})


def record_login(request, user):
    """Audit sign-ins in each organization the person belongs to."""
    for membership in user.organization_memberships.filter(active=True).select_related("organization"):
        record_event(
            organization=membership.organization,
            action="auth.login",
            entity=membership,
            actor=user,
            request=request,
            summary={"username": user.get_username()},
        )
