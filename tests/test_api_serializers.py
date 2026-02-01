"""Tests for API serializers."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.api.serializers import (
    ChatMessageInputSerializer,
    ChatResponseSerializer,
    ConversationListSerializer,
    ConversationSerializer,
    HealthCheckSerializer,
    MarketplaceSerializer,
    MessageSerializer,
    ProductResultSerializer,
    SearchResultsSerializer,
)
from apps.chat.models import Conversation, Message


@pytest.fixture()
def user(db: None) -> User:
    """Create a test user."""
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
        selected_marketplaces=["MLC", "EBAY_US"],
    )


@pytest.fixture()
def message(conversation: Conversation) -> Message:
    """Create a test message."""
    return Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content="Find me a laptop",
    )


class TestMessageSerializer:
    """Tests for MessageSerializer."""

    def test_serialize_message(self, message: Message) -> None:
        """MessageSerializer should serialize message correctly."""
        serializer = MessageSerializer(message)
        data = serializer.data

        assert data["id"] == str(message.id)
        assert data["role"] == "user"
        assert data["content"] == "Find me a laptop"
        assert data["is_user_message"] is True
        assert data["is_assistant_message"] is False
        assert data["has_results"] is False

    def test_serialize_assistant_message(self, conversation: Conversation) -> None:
        """MessageSerializer should serialize assistant message."""
        msg = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Here are some laptops",
            search_results={"products": []},
        )
        serializer = MessageSerializer(msg)
        data = serializer.data

        assert data["role"] == "assistant"
        assert data["is_assistant_message"] is True
        assert data["has_results"] is True


class TestConversationSerializer:
    """Tests for ConversationSerializer."""

    def test_serialize_conversation(self, conversation: Conversation) -> None:
        """ConversationSerializer should serialize conversation."""
        serializer = ConversationSerializer(conversation)
        data = serializer.data

        assert data["id"] == str(conversation.id)
        assert data["title"] == "Test Conversation"
        assert data["selected_marketplaces"] == ["MLC", "EBAY_US"]
        assert data["is_active"] is True
        assert "messages" in data

    def test_serialize_with_messages(self, conversation: Conversation, message: Message) -> None:
        """ConversationSerializer should include messages."""
        serializer = ConversationSerializer(conversation)
        data = serializer.data

        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "Find me a laptop"


class TestConversationListSerializer:
    """Tests for ConversationListSerializer."""

    def test_serialize_conversation_list(self, conversation: Conversation) -> None:
        """ConversationListSerializer should not include messages."""
        serializer = ConversationListSerializer(conversation)
        data = serializer.data

        assert data["id"] == str(conversation.id)
        assert "messages" not in data
        assert data["message_count"] == 0


class TestChatMessageInputSerializer:
    """Tests for ChatMessageInputSerializer."""

    def test_valid_input(self) -> None:
        """ChatMessageInputSerializer should accept valid input."""
        serializer = ChatMessageInputSerializer(
            data={
                "content": "Find me a laptop",
                "marketplaces": ["MLC", "EBAY_US"],
            }
        )

        assert serializer.is_valid()
        assert serializer.validated_data["content"] == "Find me a laptop"
        assert serializer.validated_data["marketplaces"] == ["MLC", "EBAY_US"]

    def test_content_required(self) -> None:
        """ChatMessageInputSerializer should require content."""
        serializer = ChatMessageInputSerializer(data={})

        assert not serializer.is_valid()
        assert "content" in serializer.errors

    def test_empty_content_invalid(self) -> None:
        """ChatMessageInputSerializer should reject empty content."""
        serializer = ChatMessageInputSerializer(data={"content": ""})

        assert not serializer.is_valid()

    def test_whitespace_content_invalid(self) -> None:
        """ChatMessageInputSerializer should reject whitespace-only content.

        DRF CharField has trim_whitespace=True by default, so whitespace
        becomes empty string which fails min_length=1.
        """
        serializer = ChatMessageInputSerializer(data={"content": "   "})

        assert not serializer.is_valid()
        assert "content" in serializer.errors

    def test_content_trimmed(self) -> None:
        """ChatMessageInputSerializer should trim content (DRF default)."""
        serializer = ChatMessageInputSerializer(data={"content": "  Find me a laptop  "})

        assert serializer.is_valid()
        # DRF trims whitespace by default
        assert serializer.validated_data["content"] == "Find me a laptop"

    def test_marketplaces_optional(self) -> None:
        """ChatMessageInputSerializer should make marketplaces optional."""
        serializer = ChatMessageInputSerializer(data={"content": "Hello"})

        assert serializer.is_valid()
        assert serializer.validated_data["marketplaces"] == []


class TestProductResultSerializer:
    """Tests for ProductResultSerializer."""

    def test_serialize_product(self) -> None:
        """ProductResultSerializer should serialize product data."""
        data = {
            "id": "123",
            "marketplace_code": "MLC",
            "marketplace_name": "MercadoLibre Chile",
            "title": "Gaming Laptop",
            "price": Decimal("999.99"),
            "currency": "CLP",
            "url": "https://example.com/123",
            "image_url": "https://example.com/img.jpg",
            "seller_name": "TechStore",
            "seller_rating": 4.5,
            "condition": "new",
            "shipping_cost": Decimal("10.00"),
            "free_shipping": False,
            "is_best_price": True,
            "price_rank": 1,
        }
        serializer = ProductResultSerializer(data=data)

        assert serializer.is_valid()

    def test_minimal_product(self) -> None:
        """ProductResultSerializer should work with minimal data."""
        data = {
            "id": "123",
            "marketplace_code": "MLC",
            "marketplace_name": "MercadoLibre Chile",
            "title": "Laptop",
            "price": Decimal("100"),
            "currency": "CLP",
            "url": "https://example.com/123",
        }
        serializer = ProductResultSerializer(data=data)

        assert serializer.is_valid()


class TestSearchResultsSerializer:
    """Tests for SearchResultsSerializer."""

    def test_serialize_results(self) -> None:
        """SearchResultsSerializer should serialize search results."""
        data = {
            "products": [],
            "total_count": 100,
            "query": "laptop",
            "has_more": True,
            "successful_marketplaces": 2,
            "failed_marketplaces": [],
        }
        serializer = SearchResultsSerializer(data=data)

        assert serializer.is_valid()


class TestChatResponseSerializer:
    """Tests for ChatResponseSerializer."""

    def test_serialize_response(self, message: Message) -> None:
        """ChatResponseSerializer should serialize chat response."""
        msg_data = MessageSerializer(message).data
        data = {
            "message": msg_data,
            "search_results": None,
        }
        serializer = ChatResponseSerializer(data=data)

        assert serializer.is_valid()


class TestMarketplaceSerializer:
    """Tests for MarketplaceSerializer."""

    def test_serialize_marketplace(self) -> None:
        """MarketplaceSerializer should serialize marketplace data."""
        data = {
            "code": "MLC",
            "name": "MercadoLibre Chile",
            "country": "Chile",
            "is_available": True,
        }
        serializer = MarketplaceSerializer(data=data)

        assert serializer.is_valid()


class TestHealthCheckSerializer:
    """Tests for HealthCheckSerializer."""

    def test_serialize_health(self) -> None:
        """HealthCheckSerializer should serialize health data."""
        data = {
            "status": "healthy",
            "version": "0.1.0",
            "services": {"database": True, "cache": True},
        }
        serializer = HealthCheckSerializer(data=data)

        assert serializer.is_valid()
