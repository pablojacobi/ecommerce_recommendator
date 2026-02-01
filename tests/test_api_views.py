"""Tests for API views."""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Conversation, Message


@pytest.fixture()
def api_client() -> APIClient:
    """Create an API test client."""
    return APIClient()


@pytest.fixture()
def user(db: None) -> User:
    """Create a test user."""
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture()
def authenticated_client(api_client: APIClient, user: User) -> APIClient:
    """Create an authenticated API client."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture()
def conversation(user: User) -> Conversation:
    """Create a test conversation."""
    return Conversation.objects.create(
        user=user,
        title="Test Conversation",
        selected_marketplaces=["MLC"],
    )


@pytest.fixture()
def message(conversation: Conversation) -> Message:
    """Create a test message."""
    return Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content="Find me a laptop",
    )


class TestConversationViewSet:
    """Tests for ConversationViewSet."""

    def test_list_conversations_unauthenticated(self, api_client: APIClient) -> None:
        """Unauthenticated requests should be rejected."""
        url = reverse("api:conversation-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_conversations(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Authenticated user should see their conversations."""
        url = reverse("api:conversation-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(conversation.id)

    def test_list_conversations_only_own(self, authenticated_client: APIClient, user: User) -> None:
        """User should only see their own conversations."""
        # Create another user with a conversation
        other_user = User.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="testpass123",
        )
        Conversation.objects.create(user=other_user, title="Other's convo")

        url = reverse("api:conversation-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 0

    def test_create_conversation(self, authenticated_client: APIClient) -> None:
        """User should be able to create a conversation."""
        url = reverse("api:conversation-list")
        response = authenticated_client.post(
            url,
            data={"selected_marketplaces": ["MLC", "EBAY_US"]},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["selected_marketplaces"] == ["MLC", "EBAY_US"]

    def test_retrieve_conversation(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """User should be able to retrieve their conversation."""
        url = reverse("api:conversation-detail", args=[conversation.id])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(conversation.id)
        assert "messages" in response.data

    def test_update_conversation(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """User should be able to update their conversation."""
        url = reverse("api:conversation-detail", args=[conversation.id])
        response = authenticated_client.patch(
            url,
            data={"title": "Updated Title"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["title"] == "Updated Title"

    def test_delete_conversation(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """User should be able to delete their conversation."""
        url = reverse("api:conversation-detail", args=[conversation.id])
        response = authenticated_client.delete(url)

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not Conversation.objects.filter(id=conversation.id).exists()


class TestConversationChatEndpoint:
    """Tests for the chat endpoint."""

    def test_chat_unauthenticated(self, api_client: APIClient, conversation: Conversation) -> None:
        """Unauthenticated chat should be rejected."""
        url = reverse("api:conversation-chat", args=[conversation.id])
        response = api_client.post(
            url,
            data={"content": "Hello"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_chat_success(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Chat should create messages and return response."""
        from unittest.mock import patch

        from services.chat.types import ChatResponse

        mock_response = ChatResponse(message="Found laptops for you!")

        url = reverse("api:conversation-chat", args=[conversation.id])
        with patch(
            "apps.api.views.ConversationViewSet._invoke_chat_service",
            return_value=mock_response,
        ):
            response = authenticated_client.post(
                url,
                data={"content": "Find me a laptop"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert "message" in response.data

        # Should have created 2 messages (user + assistant)
        assert conversation.messages.count() == 2

    def test_chat_updates_title(self, authenticated_client: APIClient, user: User) -> None:
        """First message should update conversation title."""
        from unittest.mock import patch

        from services.chat.types import ChatResponse

        mock_response = ChatResponse(message="Found laptops!")

        convo = Conversation.objects.create(user=user, title="")
        url = reverse("api:conversation-chat", args=[convo.id])
        with patch(
            "apps.api.views.ConversationViewSet._invoke_chat_service",
            return_value=mock_response,
        ):
            response = authenticated_client.post(
                url,
                data={"content": "Find me a gaming laptop"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        convo.refresh_from_db()
        assert convo.title == "Find me a gaming laptop"

    def test_chat_updates_marketplaces(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Chat should update conversation marketplaces if provided."""
        from unittest.mock import patch

        from services.chat.types import ChatResponse

        mock_response = ChatResponse(message="Found results!")

        url = reverse("api:conversation-chat", args=[conversation.id])
        with patch(
            "apps.api.views.ConversationViewSet._invoke_chat_service",
            return_value=mock_response,
        ):
            response = authenticated_client.post(
                url,
                data={
                    "content": "Find laptops",
                    "marketplaces": ["EBAY_US", "EBAY_GB"],
                },
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        conversation.refresh_from_db()
        assert conversation.selected_marketplaces == ["EBAY_US", "EBAY_GB"]

    def test_chat_invalid_content(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Chat should reject empty content."""
        url = reverse("api:conversation-chat", args=[conversation.id])
        response = authenticated_client.post(
            url,
            data={"content": ""},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_whitespace_content(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Chat should reject whitespace-only content."""
        url = reverse("api:conversation-chat", args=[conversation.id])
        response = authenticated_client.post(
            url,
            data={"content": "   "},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_chat_handles_exception(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Chat should handle processing exceptions gracefully."""
        from unittest.mock import patch

        url = reverse("api:conversation-chat", args=[conversation.id])

        # Mock _process_chat_message to raise an exception
        with patch(
            "apps.api.views.ConversationViewSet._process_chat_message",
            side_effect=RuntimeError("Processing error"),
        ):
            response = authenticated_client.post(
                url,
                data={"content": "Test message"},
                format="json",
            )

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "error" in response.data

    def test_chat_with_search_results(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Chat should return search results when available."""
        from decimal import Decimal
        from unittest.mock import patch

        from services.chat.types import ChatResponse
        from services.gemini.types import SearchIntent
        from services.marketplaces.base import ProductResult, SortOrder
        from services.search.types import AggregatedResult, EnrichedProduct

        product = ProductResult(
            id="prod-123",
            marketplace_code="MLC",
            title="Test Laptop",
            price=Decimal("999.99"),
            currency="CLP",
            url="https://example.com/laptop",
            image_url="https://example.com/img.jpg",
            seller_name="Store",
            seller_rating=4.5,
            condition="new",
            shipping_cost=Decimal("10"),
            free_shipping=False,
        )
        enriched = EnrichedProduct(
            product=product,
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
            is_best_price=True,
            price_rank=1,
        )
        search_results = AggregatedResult(
            products=[enriched],
            total_count=1,
            query="laptop",
            has_more=False,
        )
        search_intent = SearchIntent(
            query="laptop",
            original_query="Find laptop",
            sort_order=SortOrder.PRICE_ASC,
            min_price=Decimal("100"),
            max_price=Decimal("2000"),
            limit=20,
        )
        mock_response = ChatResponse(
            message="Found laptops!",
            search_results=search_results,
            search_intent=search_intent,
        )

        url = reverse("api:conversation-chat", args=[conversation.id])
        with patch(
            "apps.api.views.ConversationViewSet._invoke_chat_service",
            return_value=mock_response,
        ):
            response = authenticated_client.post(
                url,
                data={"content": "Find laptop"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["search_results"] is not None
        assert response.data["search_results"]["total_count"] == 1
        assert len(response.data["search_results"]["products"]) == 1

    def test_chat_integration_with_mocked_services(
        self, authenticated_client: APIClient, conversation: Conversation
    ) -> None:
        """Integration test: exercise full path with mocked external services."""
        from decimal import Decimal
        from unittest.mock import AsyncMock, MagicMock, patch

        from core.result import success
        from services.gemini.types import IntentType, SearchIntent
        from services.marketplaces.base import ProductResult, SortOrder
        from services.search.types import AggregatedResult, EnrichedProduct

        # Create mock search results
        product = ProductResult(
            id="prod-456",
            marketplace_code="MLC",
            title="Gaming Laptop",
            price=Decimal("1500"),
            currency="CLP",
            url="https://example.com/gaming",
            image_url=None,
            seller_name=None,
            seller_rating=None,
            condition="new",
            shipping_cost=None,
            free_shipping=True,
        )
        enriched = EnrichedProduct(
            product=product,
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
            is_best_price=False,
            price_rank=1,
        )
        search_intent = SearchIntent(
            query="gaming laptop",
            original_query="Test query",
            sort_order=SortOrder.RELEVANCE,
            limit=20,
        )
        search_results = AggregatedResult(
            products=[enriched],
            total_count=10,
            query="gaming laptop",
            has_more=True,
        )

        # Setup mock gemini service
        mock_gemini_cls = MagicMock()
        mock_gemini = MagicMock()
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(search_intent))
        mock_gemini_cls.return_value = mock_gemini

        # Setup mock search orchestrator
        mock_orchestrator_cls = MagicMock()
        mock_orchestrator = MagicMock()
        mock_orchestrator.search = AsyncMock(return_value=success(search_results))
        mock_orchestrator.close = AsyncMock()
        mock_orchestrator_cls.return_value = mock_orchestrator

        # Setup mock factory
        mock_factory_cls = MagicMock()

        conversation.selected_marketplaces = ["MLC"]
        conversation.save()

        url = reverse("api:conversation-chat", args=[conversation.id])
        with (
            patch("services.gemini.service.GeminiService", mock_gemini_cls),
            patch("services.search.orchestrator.SearchOrchestrator", mock_orchestrator_cls),
            patch("services.marketplaces.factory.MarketplaceFactory", mock_factory_cls),
        ):
            response = authenticated_client.post(
                url,
                data={"content": "Find gaming laptop"},
                format="json",
            )

        assert response.status_code == status.HTTP_200_OK
        assert "message" in response.data
        # Verify services were called
        mock_gemini.classify_intent.assert_called_once()
        mock_orchestrator.search.assert_called_once()


class TestConversationClearEndpoint:
    """Tests for the clear endpoint."""

    def test_clear_messages(
        self,
        authenticated_client: APIClient,
        conversation: Conversation,
        message: Message,
    ) -> None:
        """Clear should delete all messages."""
        url = reverse("api:conversation-clear", args=[conversation.id])
        response = authenticated_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "cleared"
        assert conversation.messages.count() == 0

    def test_clear_resets_title(
        self,
        authenticated_client: APIClient,
        conversation: Conversation,
    ) -> None:
        """Clear should reset conversation title."""
        conversation.title = "Some Title"
        conversation.save()

        url = reverse("api:conversation-clear", args=[conversation.id])
        authenticated_client.post(url)

        conversation.refresh_from_db()
        assert conversation.title == ""


class TestMessageViewSet:
    """Tests for MessageViewSet."""

    def test_list_messages_unauthenticated(self, api_client: APIClient) -> None:
        """Unauthenticated requests should be rejected."""
        url = reverse("api:message-list")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_messages(self, authenticated_client: APIClient, message: Message) -> None:
        """Authenticated user should see their messages."""
        url = reverse("api:message-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["count"] == 1

    def test_retrieve_message(self, authenticated_client: APIClient, message: Message) -> None:
        """User should be able to retrieve their message."""
        url = reverse("api:message-detail", args=[message.id])
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["id"] == str(message.id)

    def test_messages_read_only(self, authenticated_client: APIClient, message: Message) -> None:
        """Messages should be read-only (no create/update/delete via API)."""
        # Create
        url = reverse("api:message-list")
        response = authenticated_client.post(url, data={}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

        # Update
        url = reverse("api:message-detail", args=[message.id])
        response = authenticated_client.patch(url, data={"content": "new"}, format="json")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

        # Delete
        response = authenticated_client.delete(url)
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class TestMarketplacesView:
    """Tests for MarketplacesView."""

    def test_list_marketplaces_unauthenticated(self, api_client: APIClient) -> None:
        """Unauthenticated requests should be rejected."""
        url = reverse("api:marketplaces")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_list_marketplaces(self, authenticated_client: APIClient) -> None:
        """Authenticated user should see marketplaces."""
        url = reverse("api:marketplaces")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) > 0

        # Check structure
        mp = response.data[0]
        assert "code" in mp
        assert "name" in mp
        assert "country" in mp
        assert "is_available" in mp


class TestHealthCheckView:
    """Tests for HealthCheckView."""

    def test_health_check_no_auth(self, api_client: APIClient) -> None:
        """Health check should work without authentication."""
        url = reverse("api:health")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert "version" in response.data
        assert "services" in response.data
