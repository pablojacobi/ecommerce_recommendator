"""Tests for chat app views."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client
from django.urls import reverse

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
        title="Test conversation",
    )


@pytest.fixture()
def client() -> Client:
    """Return Django test client."""
    return Client()


@pytest.mark.django_db
class TestChatIndexView:
    """Tests for chat index view."""

    def test_index_renders_for_authenticated_user(self, client: Client, user: User) -> None:
        """Chat index renders for authenticated user."""
        client.force_login(user)
        response = client.get(reverse("chat:index"))

        assert response.status_code == 200
        assert b"Asistente de Compras" in response.content

    def test_index_requires_login(self, client: Client) -> None:
        """Chat index requires authentication."""
        response = client.get(reverse("chat:index"))

        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_index_creates_conversation_if_none(self, client: Client, user: User) -> None:
        """Chat index creates conversation if user has none."""
        client.force_login(user)
        assert Conversation.objects.filter(user=user).count() == 0

        client.get(reverse("chat:index"))

        assert Conversation.objects.filter(user=user).count() == 1

    def test_index_uses_existing_conversation(
        self, client: Client, user: User, conversation: Conversation
    ) -> None:
        """Chat index uses existing conversation."""
        client.force_login(user)

        response = client.get(reverse("chat:index"))

        assert response.status_code == 200
        assert str(conversation.id) in response.content.decode()

    def test_index_includes_marketplace_selector(self, client: Client, user: User) -> None:
        """Chat index includes marketplace checkboxes."""
        client.force_login(user)
        response = client.get(reverse("chat:index"))

        content = response.content.decode()
        assert "EBAY_US" in content
        assert "MLC" in content
        assert "marketplace" in content


@pytest.mark.django_db
class TestSendMessageView:
    """Tests for send message HTMX view."""

    def test_send_message_requires_login(self, client: Client) -> None:
        """Send message requires authentication."""
        response = client.post(reverse("chat:send_message"))

        assert response.status_code == 302
        assert "login" in response["Location"]

    def test_send_message_requires_post(self, client: Client, user: User) -> None:
        """Send message only accepts POST."""
        client.force_login(user)
        response = client.get(reverse("chat:send_message"))

        assert response.status_code == 405

    def test_send_message_requires_message(
        self, client: Client, user: User, conversation: Conversation
    ) -> None:
        """Send message requires message content."""
        client.force_login(user)
        response = client.post(
            reverse("chat:send_message"),
            {"conversation_id": str(conversation.id)},
        )

        assert response.status_code == 400

    @patch("apps.chat.views._process_chat")
    def test_send_message_success(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
        conversation: Conversation,
    ) -> None:
        """Send message returns HTML with user and assistant messages."""
        mock_process.return_value = {
            "message": "Encontré 5 productos para 'laptop'",
            "products": [],
            "has_more": False,
        }

        client.force_login(user)
        response = client.post(
            reverse("chat:send_message"),
            {
                "message": "Busco un laptop",
                "conversation_id": str(conversation.id),
                "marketplaces": "EBAY_US,MLC",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        # User message should be in response
        assert "Busco un laptop" in content
        # Assistant message should be in response
        assert "Encontr" in content

    @patch("apps.chat.views._process_chat")
    def test_send_message_saves_messages(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
        conversation: Conversation,
    ) -> None:
        """Send message saves both user and assistant messages."""
        mock_process.return_value = {
            "message": "Here are some results",
            "products": [],
            "has_more": False,
        }

        client.force_login(user)
        client.post(
            reverse("chat:send_message"),
            {
                "message": "Find a laptop",
                "conversation_id": str(conversation.id),
                "marketplaces": "EBAY_US",
            },
        )

        messages = Message.objects.filter(conversation=conversation).order_by("created_at")
        assert messages.count() == 2
        assert messages[0].role == Message.Role.USER
        assert messages[0].content == "Find a laptop"
        assert messages[1].role == Message.Role.ASSISTANT

    @patch("apps.chat.views._process_chat")
    def test_send_message_with_products(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
        conversation: Conversation,
    ) -> None:
        """Send message includes products in response."""
        mock_process.return_value = {
            "message": "Found products",
            "products": [
                {
                    "id": "123",
                    "title": "Gaming Laptop RTX 4060",
                    "price": Decimal("999.99"),
                    "currency": "USD",
                    "url": "https://example.com/123",
                    "image_url": "https://example.com/img.jpg",
                    "marketplace_code": "EBAY_US",
                    "marketplace_name": "eBay United States",
                    "seller_rating": 4.5,
                    "shipping_cost": None,
                    "free_shipping": True,
                    "is_best_price": True,
                    "tax_info": None,
                },
            ],
            "has_more": True,
        }

        client.force_login(user)
        response = client.post(
            reverse("chat:send_message"),
            {
                "message": "Find laptop",
                "conversation_id": str(conversation.id),
                "marketplaces": "EBAY_US",
            },
        )

        content = response.content.decode()
        assert "Gaming Laptop RTX 4060" in content
        assert "Mejor Precio" in content
        assert "eBay United States" in content

    @patch("apps.chat.views._process_chat")
    def test_send_message_with_tax_info(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
        conversation: Conversation,
    ) -> None:
        """Send message includes tax breakdown when available."""
        mock_process.return_value = {
            "message": "Found products",
            "products": [
                {
                    "id": "123",
                    "title": "Laptop",
                    "price": Decimal("100"),
                    "currency": "USD",
                    "url": "https://example.com/123",
                    "image_url": None,
                    "marketplace_code": "EBAY_US",
                    "marketplace_name": "eBay US",
                    "seller_rating": None,
                    "shipping_cost": Decimal("20"),
                    "free_shipping": False,
                    "is_best_price": False,
                    "tax_info": {
                        "customs_duty": Decimal("6.00"),
                        "vat": Decimal("23.94"),
                        "total_taxes": Decimal("29.94"),
                        "total_with_taxes": Decimal("149.94"),
                        "de_minimis_applied": False,
                    },
                },
            ],
            "has_more": False,
        }

        client.force_login(user)
        response = client.post(
            reverse("chat:send_message"),
            {
                "message": "Find laptop",
                "conversation_id": str(conversation.id),
                "marketplaces": "EBAY_US",
                "destination_country": "CL",
            },
        )

        content = response.content.decode()
        assert "Arancel" in content
        assert "IVA" in content
        assert "Total estimado" in content

    @patch("apps.chat.views._process_chat")
    def test_send_message_creates_conversation_if_invalid(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
    ) -> None:
        """Send message creates new conversation if ID is invalid."""
        mock_process.return_value = {
            "message": "Response",
            "products": [],
            "has_more": False,
        }

        client.force_login(user)
        client.post(
            reverse("chat:send_message"),
            {
                "message": "Hello",
                "conversation_id": "invalid-uuid",
                "marketplaces": "MLC",
            },
        )

        # Should have created a new conversation
        assert Conversation.objects.filter(user=user).count() == 1

    @patch("apps.chat.views._process_chat")
    def test_send_message_creates_conversation_if_no_id(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
    ) -> None:
        """Send message creates new conversation if no ID provided."""
        mock_process.return_value = {
            "message": "Response",
            "products": [],
            "has_more": False,
        }

        client.force_login(user)
        client.post(
            reverse("chat:send_message"),
            {
                "message": "Hello there",
                "marketplaces": "MLC",
                # No conversation_id
            },
        )

        # Should have created a new conversation
        conv = Conversation.objects.filter(user=user).first()
        assert conv is not None
        assert conv.title == "Hello there"

    @patch("apps.chat.views._process_chat")
    def test_send_message_uses_default_marketplaces(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
        conversation: Conversation,
    ) -> None:
        """Send message uses default marketplaces if none provided."""
        mock_process.return_value = {
            "message": "Response",
            "products": [],
            "has_more": False,
        }

        client.force_login(user)
        client.post(
            reverse("chat:send_message"),
            {
                "message": "Hello",
                "conversation_id": str(conversation.id),
                # No marketplaces provided
            },
        )

        # Check that _process_chat was called with default marketplaces
        call_kwargs = mock_process.call_args[1]
        assert "EBAY_US" in call_kwargs["marketplaces"]
        assert "MLC" in call_kwargs["marketplaces"]

    @patch("apps.chat.views._process_chat")
    def test_send_message_handles_error(
        self,
        mock_process: MagicMock,
        client: Client,
        user: User,
        conversation: Conversation,
    ) -> None:
        """Send message returns error message on exception."""
        mock_process.side_effect = RuntimeError("Something went wrong")

        client.force_login(user)
        response = client.post(
            reverse("chat:send_message"),
            {
                "message": "Hello",
                "conversation_id": str(conversation.id),
                "marketplaces": "MLC",
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert "error" in content.lower() or "Lo siento" in content


@pytest.mark.django_db
class TestLoadMoreView:
    """Tests for load more HTMX view."""

    def test_load_more_requires_login(self, client: Client) -> None:
        """Load more requires authentication."""
        response = client.post(reverse("chat:load_more"))

        assert response.status_code == 302

    def test_load_more_requires_post(self, client: Client, user: User) -> None:
        """Load more only accepts POST."""
        client.force_login(user)
        response = client.get(reverse("chat:load_more"))

        assert response.status_code == 405

    def test_load_more_returns_empty(self, client: Client, user: User) -> None:
        """Load more returns empty for now (pagination not implemented)."""
        client.force_login(user)
        response = client.post(reverse("chat:load_more"))

        assert response.status_code == 200
        assert response.content == b""
