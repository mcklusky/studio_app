from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.filters import SearchFilter
from rest_framework.permissions import IsAuthenticated

from apps.audit.services import changed_fields, record_event
from apps.identity.permissions import HasBusinessPermission
from apps.identity.scope import focus_on_view, resolve_membership


class ScopedViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """Organization-scoped CRUD (no delete) with per-action permission codes and audit events.

    Subclasses set read/create/update permission codes and implement get_queryset()
    using self.get_membership(). Actions without a mapped code are denied.
    """

    permission_classes = [IsAuthenticated, HasBusinessPermission]
    filter_backends = [SearchFilter]
    read_permission = None
    create_permission = None
    update_permission = None
    extra_action_permissions = {}

    def get_required_permission(self, _request):
        action = getattr(self, "action", None)
        mapping = {
            "list": self.read_permission,
            "retrieve": self.read_permission,
            "create": self.create_permission,
            "update": self.update_permission,
            "partial_update": self.update_permission,
            **self.extra_action_permissions,
        }
        return mapping.get(action)

    def get_membership(self):
        if not hasattr(self.request, "membership"):
            membership = resolve_membership(self.request.user, self.request.headers.get("X-Organization-ID"))
            self.request.membership = focus_on_view(membership, self.request)
        return self.request.membership

    def audit_name(self):
        return self.get_serializer_class().Meta.model._meta.model_name

    def get_create_kwargs(self):
        return {"organization": self.get_membership().organization}

    def perform_create(self, serializer):
        with transaction.atomic():
            instance = serializer.save(**self.get_create_kwargs())
            record_event(
                organization=self.get_membership().organization,
                action=f"{self.audit_name()}.created",
                entity=instance,
                request=self.request,
                summary=changed_fields(instance, serializer.validated_data),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            instance = serializer.save()
            record_event(
                organization=self.get_membership().organization,
                action=f"{self.audit_name()}.updated",
                entity=instance,
                request=self.request,
                summary=changed_fields(instance, serializer.validated_data),
            )
