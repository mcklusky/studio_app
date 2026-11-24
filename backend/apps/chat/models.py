import uuid

from django.conf import settings
from django.db import models

from apps.organizations.models import Organization


class Conversation(models.Model):
    """A staff chat thread inside one organization.

    TEAM: one per organization; every active member can read and post.
    DIRECT: two people; only they can read and post, and only while both are active staff.
    """

    class Kind(models.TextChoices):
        TEAM = "team", "Team"
        DIRECT = "direct", "Direct"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="conversations")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    # DIRECT: both user IDs, sorted and joined, so a pair never gets two threads. TEAM: empty.
    direct_key = models.CharField(max_length=80, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "kind", "direct_key"], name="uniq_conversation_per_pair"),
        ]


class ConversationMember(models.Model):
    """Who is in a direct thread, and how far each person has read (team threads add a row on first read)."""

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_memberships")
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="uniq_conversation_member")]


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="chat_messages")
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"], name="chat_msg_conv_time")]
