from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.scope import resolve_membership
from apps.notifications.services import build_alerts, mark_read


class AlertsView(APIView):
    """GET: current alerts for the signed-in person. POST read/: mark keys (or all) as read."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        alerts = build_alerts(membership, request.user)
        return Response({"unread": sum(1 for a in alerts if not a["read"]), "items": alerts})


class AlertsReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        membership = resolve_membership(request.user, request.headers.get("X-Organization-ID"))
        if request.data.get("all"):
            keys = [a["key"] for a in build_alerts(membership, request.user) if not a["read"]]
        else:
            keys = request.data.get("keys")
            if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
                raise ValidationError({"keys": ["Send a list of alert keys, or all: true."]})
        mark_read(membership, request.user, keys[:500])
        return Response({"marked": len(keys)})
