from django.db.models import Q
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.audit.models import AuditEvent
from apps.common.filters import date_param
from apps.identity.permissions import HasBusinessPermission


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditEvent
        fields = ("id", "actor", "actor_name", "action", "entity_type", "entity_id", "summary", "request_id", "created_at")

    def get_actor_name(self, event):
        if not event.actor_id:
            return "System"
        return event.actor.get_full_name() or event.actor.get_username()


class AuditEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasBusinessPermission]
    permission_code = "audit.view"
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        queryset = AuditEvent.objects.filter(organization_id=self.request.membership.organization_id).select_related("actor")
        params = self.request.query_params
        for param, field in (("entity_type", "entity_type"), ("entity_id", "entity_id"), ("action", "action"), ("actor", "actor_id")):
            if params.get(param):
                queryset = queryset.filter(**{field: params[param]})
        if params.get("area"):
            # e.g. area=sale,payment -> actions starting with "sale." or "payment."
            area_filter = Q()
            for area in params["area"].split(","):
                area_filter |= Q(action__startswith=f"{area.strip()}.")
            queryset = queryset.filter(area_filter)
        start, end = date_param(self.request, "from"), date_param(self.request, "to")
        if start:
            queryset = queryset.filter(created_at__date__gte=start)
        if end:
            queryset = queryset.filter(created_at__date__lte=end)
        return queryset
