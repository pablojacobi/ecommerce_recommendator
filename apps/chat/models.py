"""Models for the chat application."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """
    Represents a chat conversation session.

    Each conversation belongs to a user and contains multiple messages.
    Conversations maintain context for product recommendations.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )
    title = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Auto-generated title from first message",
    )
    selected_marketplaces = models.JSONField(
        default=list,
        blank=True,
        help_text="Marketplaces selected for this conversation",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the conversation is active",
    )

    class Meta:
        """Meta options for Conversation model."""

        db_table = "conversations"
        ordering = ["-updated_at"]
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"

    def __str__(self) -> str:
        """Return string representation of conversation."""
        return self.title or f"Conversation {self.id}"

    @property
    def message_count(self) -> int:
        """Return the number of messages in this conversation."""
        return self.messages.count()


class Message(models.Model):
    """
    Represents a single message in a conversation.

    Messages can be from the user or the assistant, and may contain
    search results with product recommendations.
    """

    class Role(models.TextChoices):
        """Message sender role."""

        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.USER,
    )
    content = models.TextField(
        help_text="Message content (user query or assistant response)",
    )
    search_results = models.JSONField(
        null=True,
        blank=True,
        help_text="Product search results returned by the assistant",
    )
    search_params = models.JSONField(
        null=True,
        blank=True,
        help_text="Parsed search parameters from user query",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        """Meta options for Message model."""

        db_table = "messages"
        ordering = ["created_at"]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self) -> str:
        """Return string representation of message."""
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"{self.role}: {preview}"

    @property
    def is_user_message(self) -> bool:
        """Check if this is a user message."""
        return self.role == self.Role.USER

    @property
    def is_assistant_message(self) -> bool:
        """Check if this is an assistant message."""
        return self.role == self.Role.ASSISTANT

    @property
    def has_results(self) -> bool:
        """Check if this message has search results."""
        return bool(self.search_results)
