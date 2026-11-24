from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.chat.models import Conversation, ConversationMember, Message
from apps.identity.models import Membership

MAX_BODY = 2000


def display_name(user):
    return user.get_full_name() or user.get_username()


def team_conversation(organization):
    conversation, _ = Conversation.objects.get_or_create(organization=organization, kind=Conversation.Kind.TEAM, direct_key="")
    return conversation


def visible_conversations(membership):
    """The team thread plus the person's direct threads whose other person is still active staff."""
    organization, user = membership.organization, membership.user
    team_conversation(organization)
    active = set(Membership.objects.filter(organization=organization, active=True).values_list("user_id", flat=True))
    rows = []
    threads = (
        Conversation.objects.filter(organization=organization)
        .filter(Q(kind=Conversation.Kind.TEAM) | Q(members__user=user))
        .distinct()
        .prefetch_related("members__user")
    )
    for conversation in threads:
        if conversation.kind == Conversation.Kind.DIRECT:
            others = [m.user for m in conversation.members.all() if m.user_id != user.pk]
            if not others or others[0].pk not in active:
                continue
        rows.append(conversation)
    return rows


def get_conversation(membership, conversation_id):
    for conversation in visible_conversations(membership):
        if str(conversation.pk) == str(conversation_id):
            return conversation
    raise NotFound("Conversation was not found.")


def open_direct(membership, other_user_id):
    organization, user = membership.organization, membership.user
    other = None
    if other_user_id:
        other = Membership.objects.filter(organization=organization, active=True, user_id=other_user_id).first()
    if other is None:
        raise ValidationError({"user": ["Choose someone on your team."]})
    if other.user_id == user.pk:
        raise ValidationError({"user": ["You cannot start a chat with yourself."]})
    key = ":".join(sorted([str(user.pk), str(other.user_id)]))
    try:
        with transaction.atomic():
            conversation, created = Conversation.objects.get_or_create(
                organization=organization, kind=Conversation.Kind.DIRECT, direct_key=key
            )
            if created:
                ConversationMember.objects.bulk_create(
                    [
                        ConversationMember(conversation=conversation, user=user),
                        ConversationMember(conversation=conversation, user_id=other.user_id),
                    ]
                )
    except IntegrityError:
        conversation = Conversation.objects.get(organization=organization, kind=Conversation.Kind.DIRECT, direct_key=key)
    return conversation


def post_message(membership, conversation, body):
    text = body.strip() if isinstance(body, str) else ""
    if not text:
        raise ValidationError({"body": ["Write a message first."]})
    if len(text) > MAX_BODY:
        raise ValidationError({"body": [f"Keep messages under {MAX_BODY} characters."]})
    with transaction.atomic():
        message = Message.objects.create(conversation=conversation, sender=membership.user, body=text)
        Conversation.objects.filter(pk=conversation.pk).update(last_message_at=message.created_at)
        mark_read(membership, conversation, at=message.created_at)
    return message


def mark_read(membership, conversation, at=None):
    at = at or timezone.now()
    member, _ = ConversationMember.objects.get_or_create(conversation=conversation, user=membership.user)
    if member.last_read_at is None or member.last_read_at < at:
        member.last_read_at = at
        member.save(update_fields=["last_read_at"])


def summaries(membership):
    """Rows for the chat panel: title, last message and unread count per thread; team first, then newest."""
    user = membership.user
    conversations = visible_conversations(membership)
    reads = dict(
        ConversationMember.objects.filter(user=user, conversation__in=[c.pk for c in conversations]).values_list(
            "conversation_id", "last_read_at"
        )
    )
    rows = []
    for conversation in conversations:
        last_read = reads.get(conversation.pk)
        # Someone new to the team starts with nothing unread rather than the whole history.
        if last_read is None and conversation.kind == Conversation.Kind.TEAM:
            last_read = membership.created_at
        unread = Message.objects.filter(conversation=conversation).exclude(sender=user)
        if last_read is not None:
            unread = unread.filter(created_at__gt=last_read)
        last = Message.objects.filter(conversation=conversation).select_related("sender").order_by("-created_at").first()
        if conversation.kind == Conversation.Kind.TEAM:
            title, other = "Team chat", None
        else:
            other_user = next(m.user for m in conversation.members.all() if m.user_id != user.pk)
            title, other = display_name(other_user), str(other_user.pk)
        rows.append(
            {
                "id": str(conversation.pk),
                "kind": conversation.kind,
                "title": title,
                "other_user": other,
                "unread": unread.count(),
                "last_message": (
                    {
                        "body": last.body[:140],
                        "sender_name": "You" if last.sender_id == user.pk else display_name(last.sender),
                        "created_at": last.created_at,
                    }
                    if last
                    else None
                ),
                "updated_at": conversation.last_message_at or conversation.created_at,
            }
        )
    rows.sort(key=lambda r: (r["kind"] != Conversation.Kind.TEAM, -r["updated_at"].timestamp()))
    return rows


def message_payload(message, user):
    return {
        "id": str(message.id),
        "body": message.body,
        "sender": str(message.sender_id),
        "sender_name": display_name(message.sender),
        "mine": message.sender_id == user.pk,
        "created_at": message.created_at,
    }
