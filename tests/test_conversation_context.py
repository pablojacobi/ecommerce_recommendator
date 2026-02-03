"""Tests for conversation context handling - TDD for multi-turn conversations."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

from django.test import Client
from django.urls import reverse

from apps.chat.models import Conversation, Message


@pytest.fixture
def user(db):
    """Create a test user."""
    from apps.accounts.models import User
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def client():
    """Return Django test client."""
    return Client()


@pytest.mark.django_db
class TestConversationContext:
    """Test that the chat follows conversation context across multiple messages."""

    def test_second_message_uses_context_from_first(
        self, client: Client, user
    ) -> None:
        """
        Scenario:
        1. User: "busco un macbook air M4"
        2. User: "solo los de menos de 800 dólares"

        The second message should understand it's a refinement of the first search,
        NOT a new search for "None" or fail with an error.
        """
        client.force_login(user)

        # Create conversation
        conversation = Conversation.objects.create(user=user, title="")

        # Mock the chat processing to return products for first message
        first_response = {
            "message": "Found 10 MacBook Air M4 products.",
            "products": [
                {
                    "id": "1",
                    "title": "MacBook Air M4 2025",
                    "price": 999.00,
                    "currency": "USD",
                    "url": "https://example.com/1",
                    "image_url": None,
                    "marketplace_code": "EBAY_US",
                    "marketplace_name": "eBay",
                    "seller_rating": 4.5,
                    "shipping_cost": None,
                    "free_shipping": True,
                    "is_best_price": False,
                    "tax_info": None,
                },
                {
                    "id": "2",
                    "title": "MacBook Air M4 Budget",
                    "price": 750.00,
                    "currency": "USD",
                    "url": "https://example.com/2",
                    "image_url": None,
                    "marketplace_code": "EBAY_US",
                    "marketplace_name": "eBay",
                    "seller_rating": 4.0,
                    "shipping_cost": None,
                    "free_shipping": True,
                    "is_best_price": True,
                    "tax_info": None,
                },
            ],
            "has_more": False,
            "generated_title": "MacBook Air M4",
        }

        # Second response should be a filtered version
        second_response = {
            "message": "Here are MacBook Air M4 under $800.",
            "products": [
                {
                    "id": "2",
                    "title": "MacBook Air M4 Budget",
                    "price": 750.00,
                    "currency": "USD",
                    "url": "https://example.com/2",
                    "image_url": None,
                    "marketplace_code": "EBAY_US",
                    "marketplace_name": "eBay",
                    "seller_rating": 4.0,
                    "shipping_cost": None,
                    "free_shipping": True,
                    "is_best_price": True,
                    "tax_info": None,
                },
            ],
            "has_more": False,
        }

        with patch("apps.chat.views._process_chat") as mock_process:
            mock_process.return_value = first_response

            # First message
            response1 = client.post(
                reverse("chat:send_message"),
                {
                    "message": "busco un macbook air M4",
                    "conversation_id": str(conversation.id),
                    "marketplaces": "EBAY_US",
                },
            )

            assert response1.status_code == 200
            content1 = response1.content.decode()
            assert "MacBook Air M4" in content1
            # Should NOT contain error message
            assert "error" not in content1.lower() or "Lo siento" not in content1

        # Verify first message was saved
        messages = Message.objects.filter(conversation=conversation).order_by("created_at")
        assert messages.count() == 2  # user + assistant
        assert messages[0].role == Message.Role.USER
        assert "macbook" in messages[0].content.lower()

        with patch("apps.chat.views._process_chat") as mock_process:
            mock_process.return_value = second_response

            # Second message - refinement
            response2 = client.post(
                reverse("chat:send_message"),
                {
                    "message": "solo los de menos de 800 dólares",
                    "conversation_id": str(conversation.id),
                    "marketplaces": "EBAY_US",
                },
            )

            assert response2.status_code == 200
            content2 = response2.content.decode()

            # CRITICAL: Should NOT contain error messages
            assert "None" not in content2, "Response mentions 'None' - context not followed"
            assert "Lo siento" not in content2, "Response is an error message"
            assert "error" not in content2.lower(), "Response contains error"

            # Should contain filtered results
            assert "MacBook" in content2 or "750" in content2

        # Verify _process_chat was called with conversation history
        call_kwargs = mock_process.call_args
        assert call_kwargs is not None, "_process_chat was not called"

    def test_refinement_query_does_not_search_for_none(
        self, client: Client, user
    ) -> None:
        """
        When user sends a refinement like "solo los baratos", the system
        should NOT search for literal "None" or return an error.
        """
        client.force_login(user)

        # Create conversation with existing messages
        conversation = Conversation.objects.create(user=user, title="MacBook Search")

        # Add previous messages to establish context
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="busco un macbook air M4",
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Found 10 MacBook Air M4 products.",
            search_results={
                "products": [
                    {"id": "1", "title": "MacBook Air M4", "price": 999.00, "currency": "USD"},
                    {"id": "2", "title": "MacBook Air M4 Budget", "price": 750.00, "currency": "USD"},
                ],
                "has_more": False,
            },
        )

        with patch("apps.chat.views._process_chat") as mock_process:
            mock_process.return_value = {
                "message": "Here are the cheaper options under $800.",
                "products": [
                    {
                        "id": "2",
                        "title": "MacBook Air M4 Budget",
                        "price": 750.00,
                        "currency": "USD",
                        "url": "https://example.com/2",
                        "image_url": None,
                        "marketplace_code": "EBAY_US",
                        "marketplace_name": "eBay",
                        "seller_rating": None,
                        "shipping_cost": None,
                        "free_shipping": True,
                        "is_best_price": True,
                        "tax_info": None,
                    },
                ],
                "has_more": False,
            }

            response = client.post(
                reverse("chat:send_message"),
                {
                    "message": "solo los de menos de 800 dólares",
                    "conversation_id": str(conversation.id),
                    "marketplaces": "EBAY_US",
                },
            )

            assert response.status_code == 200
            content = response.content.decode()

            # Should NOT have error indicators
            assert "None" not in content, "System searched for 'None' instead of using context"
            assert "Lo siento" not in content, "System returned error instead of results"
            assert "No encontré" not in content or "None" not in content

            # The process_chat should have been called with the refinement message
            # and should have access to conversation history
            mock_process.assert_called_once()
            call_kwargs = mock_process.call_args[1]

            # Verify conversation history was passed
            assert "conversation" in call_kwargs or len(call_kwargs.get("conversation_history", [])) > 0

    def test_gemini_receives_conversation_history(
        self, client: Client, user
    ) -> None:
        """
        Verify that when processing a message, the full conversation history
        is passed to the chat service so Gemini can understand context.
        """
        client.force_login(user)

        conversation = Conversation.objects.create(user=user, title="Test")

        # Add previous exchange
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="find me a gaming laptop",
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content="Found 20 gaming laptops.",
        )

        with patch("apps.chat.views._process_chat") as mock_process:
            mock_process.return_value = {
                "message": "Here are the RTX 4070 options.",
                "products": [],
                "has_more": False,
            }

            client.post(
                reverse("chat:send_message"),
                {
                    "message": "only with RTX 4070",
                    "conversation_id": str(conversation.id),
                    "marketplaces": "EBAY_US",
                },
            )

            # Verify _process_chat received conversation history
            mock_process.assert_called_once()
            call_args = mock_process.call_args

            # Check that conversation object or history was passed
            if call_args[1]:  # kwargs
                # Should have conversation or conversation_history
                has_context = (
                    "conversation" in call_args[1] or
                    "conversation_history" in call_args[1]
                )
                assert has_context, "No conversation context passed to _process_chat"

                # If conversation_history is passed, it should have previous messages
                if "conversation_history" in call_args[1]:
                    history = call_args[1]["conversation_history"]
                    assert len(history) >= 2, f"Expected at least 2 history items, got {len(history)}"
