from django.utils.dateparse import parse_datetime
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.chat.models import Message
from apps.chat.services import display_name, get_conversation, mark_read, message_payload, open_direct, post_message, summaries
from apps.identity.models import Membership
from apps.identity.scope import resolve_membership

PAGE = 60


def _membership(request):
    return resolve_membership(request.user, request.headers.get("X-Organization-ID"))


class ConversationListView(APIView):
    """GET: the team thread and your direct threads. POST {user}: open (or reuse) a direct thread."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = summaries(_membership(request))
        return Response({"unread": sum(r["unread"] for r in rows), "results": rows})

    def post(self, request):
        membership = _membership(request)
        conversation = open_direct(membership, request.data.get("user"))
        row = next(r for r in summaries(membership) if r["id"] == str(conversation.pk))
        return Response(row, status=201)


class MessageThrottle(ScopedRateThrottle):
    """Limits sending only; reading and polling are not throttled."""

    def allow_request(self, request, view):
        if request.method != "POST":
            return True
        return super().allow_request(request, view)


class MessageListView(APIView):
    """GET ?after=<time>: newer messages, else the latest page (?before=<time> for older). POST {body}: send."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [MessageThrottle]
    throttle_scope = "chat"

    def get(self, request, pk):
        membership = _membership(request)
        conversation = get_conversation(membership, pk)
        messages = Message.objects.filter(conversation=conversation).select_related("sender")
        after = parse_datetime(request.query_params.get("after") or "")
        before = parse_datetime(request.query_params.get("before") or "")
        if after:
            page = list(messages.filter(created_at__gt=after).order_by("created_at")[:PAGE])
        else:
            if before:
                messages = messages.filter(created_at__lt=before)
            page = list(messages.order_by("-created_at")[:PAGE])[::-1]
        return Response({"results": [message_payload(m, request.user) for m in page], "has_more": not after and len(page) == PAGE})

    def post(self, request, pk):
        membership = _membership(request)
        conversation = get_conversation(membership, pk)
        message = post_message(membership, conversation, request.data.get("body"))
        return Response(message_payload(message, request.user), status=201)


class ConversationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        membership = _membership(request)
        mark_read(membership, get_conversation(membership, pk))
        return Response({"ok": True})


class ChatPeopleView(APIView):
    """Active teammates you can message (names and roles only)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        membership = _membership(request)
        people = (
            Membership.objects.filter(organization=membership.organization, active=True)
            .exclude(user=request.user)
            .select_related("user", "role")
        )
        rows = [{"id": str(m.user_id), "name": display_name(m.user), "role": m.role.name} for m in people]
        return Response(sorted(rows, key=lambda r: r["name"].lower()))
