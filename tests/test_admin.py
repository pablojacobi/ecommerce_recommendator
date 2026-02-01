"""Tests for Django admin configurations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from apps.chat.admin import ConversationAdmin, MessageAdmin
from apps.chat.models import Conversation, Message

if TYPE_CHECKING:
    from apps.accounts.models import User


@pytest.fixture()
def user(db: None) -> User:
    """Create a test user."""
    from apps.accounts.models import User

    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture()
def conversation(user: User) -> Conversation:
    """Create a test conversation."""
    return Conversation.objects.create(user=user, title="Test")


@pytest.fixture()
def message(conversation: Conversation) -> Message:
    """Create a test message."""
    return Message.objects.create(
        conversation=conversation,
        content="Test message content",
        search_results=[{"id": 1}],
    )


@pytest.mark.django_db
class TestConversationAdmin:
    """Tests for ConversationAdmin."""

    def test_message_count_method(self, conversation: Conversation) -> None:
        """Admin message_count method returns correct count."""
        from django.contrib.admin.sites import AdminSite

        admin = ConversationAdmin(Conversation, AdminSite())
        assert admin.message_count(conversation) == 0

        Message.objects.create(conversation=conversation, content="Test")
        assert admin.message_count(conversation) == 1


@pytest.mark.django_db
class TestMessageAdmin:
    """Tests for MessageAdmin."""

    def test_short_content_short_message(self, message: Message) -> None:
        """Admin short_content returns full content for short messages."""
        from django.contrib.admin.sites import AdminSite

        admin = MessageAdmin(Message, AdminSite())
        result = admin.short_content(message)
        assert result == "Test message content"

    def test_short_content_long_message(self, conversation: Conversation) -> None:
        """Admin short_content truncates long messages."""
        from django.contrib.admin.sites import AdminSite

        long_message = Message.objects.create(
            conversation=conversation,
            content="A" * 100,
        )
        admin = MessageAdmin(Message, AdminSite())
        result = admin.short_content(long_message)
        assert result == "A" * 50 + "..."

    def test_has_results_method(self, message: Message) -> None:
        """Admin has_results method returns correct value."""
        from django.contrib.admin.sites import AdminSite

        admin = MessageAdmin(Message, AdminSite())
        assert admin.has_results(message) is True
