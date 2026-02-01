"""Tests for chat app models."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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
    return Conversation.objects.create(
        user=user,
        title="Test Conversation",
        selected_marketplaces=["EBAY_US", "MLC"],
    )


@pytest.mark.django_db
class TestConversationModel:
    """Tests for Conversation model."""

    def test_create_conversation(self, user: User) -> None:
        """Conversation can be created with required fields."""
        conversation = Conversation.objects.create(user=user)

        assert conversation.id is not None
        assert conversation.user == user
        assert conversation.title == ""
        assert conversation.is_active is True

    def test_str_with_title(self, user: User) -> None:
        """__str__ returns title when set."""
        conversation = Conversation.objects.create(
            user=user,
            title="My Test Conversation",
        )

        assert str(conversation) == "My Test Conversation"

    def test_str_without_title(self, user: User) -> None:
        """__str__ returns ID-based string when no title."""
        conversation = Conversation.objects.create(user=user)

        assert str(conversation) == f"Conversation {conversation.id}"

    def test_message_count_empty(self, conversation: Conversation) -> None:
        """message_count returns 0 for empty conversation."""
        assert conversation.message_count == 0

    def test_message_count_with_messages(self, conversation: Conversation) -> None:
        """message_count returns correct count."""
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Hello",
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Hi there!",
        )

        assert conversation.message_count == 2

    def test_selected_marketplaces_default(self, user: User) -> None:
        """selected_marketplaces defaults to empty list."""
        conversation = Conversation.objects.create(user=user)

        assert conversation.selected_marketplaces == []


@pytest.mark.django_db
class TestMessageModel:
    """Tests for Message model."""

    def test_create_user_message(self, conversation: Conversation) -> None:
        """User message can be created."""
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Find me a laptop",
        )

        assert message.id is not None
        assert message.role == Message.Role.USER
        assert message.is_user_message is True
        assert message.is_assistant_message is False

    def test_create_assistant_message(self, conversation: Conversation) -> None:
        """Assistant message can be created with search results."""
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Here are some laptops",
            search_results=[{"title": "MacBook Pro", "price": 999}],
            search_params={"query": "laptop", "sort": "price"},
        )

        assert message.is_assistant_message is True
        assert message.is_user_message is False
        assert message.has_results is True

    def test_str_short_content(self, conversation: Conversation) -> None:
        """__str__ shows full content for short messages."""
        message = Message.objects.create(
            conversation=conversation,
            content="Hello",
        )

        assert str(message) == "user: Hello"

    def test_str_long_content_truncated(self, conversation: Conversation) -> None:
        """__str__ truncates long content."""
        long_content = "A" * 100
        message = Message.objects.create(
            conversation=conversation,
            content=long_content,
        )

        assert str(message) == f"user: {'A' * 50}..."

    def test_has_results_false_when_none(self, conversation: Conversation) -> None:
        """has_results returns False when search_results is None."""
        message = Message.objects.create(
            conversation=conversation,
            content="Test",
            search_results=None,
        )

        assert message.has_results is False

    def test_has_results_false_when_empty(self, conversation: Conversation) -> None:
        """has_results returns False when search_results is empty."""
        message = Message.objects.create(
            conversation=conversation,
            content="Test",
            search_results=[],
        )

        assert message.has_results is False

    def test_message_ordering(self, conversation: Conversation) -> None:
        """Messages are ordered by created_at ascending."""
        msg1 = Message.objects.create(
            conversation=conversation,
            content="First",
        )
        msg2 = Message.objects.create(
            conversation=conversation,
            content="Second",
        )

        messages = list(conversation.messages.all())
        assert messages[0] == msg1
        assert messages[1] == msg2
