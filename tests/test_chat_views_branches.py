"""Branch-coverage tests for apps/chat/views.py.

These tests target the view functions and helpers that the main
``test_chat_views.py`` suite does not exercise (``new_conversation``,
``conversation``, ``_make_json_serializable`` fallback, ``_detect_spanish``
and ``_create_marketplace_factory``), plus the remaining ``send_message``
branches, so that the module reaches full statement and branch coverage when
this file is run on its own.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from django.test import Client
from django.urls import reverse

from apps.chat.models import Conversation
from apps.chat.views import (
    _create_marketplace_factory,
    _detect_spanish,
    _make_json_serializable,
)
from apps.search.models import Marketplace

if TYPE_CHECKING:
    from apps.accounts.models import User


@pytest.fixture()
def user(db: None) -> User:
    """Create a test user."""
    from apps.accounts.models import User

    return User.objects.create_user(
        username="branchuser",
        email="branch@example.com",
        password="branchpass123",
    )


@pytest.fixture()
def conversation(user: User) -> Conversation:
    """Create a conversation that already has a title."""
    return Conversation.objects.create(user=user, title="Existing title")


@pytest.fixture()
def client() -> Client:
    """Return a Django test client."""
    return Client()


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def test_make_json_serializable_covers_all_type_branches() -> None:
    """Recursion visits dict, list, Decimal, primitives and the str fallback."""
    weird = object()

    result = _make_json_serializable({"items": [Decimal("1.5"), "text", 1, 2.0, True, None, weird]})

    assert result == {
        "items": [1.5, "text", 1, 2.0, True, None, str(weird)],
    }


def test_detect_spanish_true_and_false() -> None:
    """Spanish indicators return True; text with none returns False."""
    assert _detect_spanish("Hola, busco un laptop") is True
    assert _detect_spanish("zzz qqq www") is False


# ---------------------------------------------------------------------------
# index view (branch on "no existing conversation")
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_index_creates_conversation_when_none(client: Client, user: User) -> None:
    """Index creates a conversation when the user has none."""
    client.force_login(user)

    response = client.get(reverse("chat:index"))

    assert response.status_code == 200
    assert Conversation.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_index_uses_existing_conversation(
    client: Client, user: User, conversation: Conversation
) -> None:
    """Index reuses the most recent conversation when one exists."""
    client.force_login(user)

    response = client.get(reverse("chat:index"))

    assert response.status_code == 200
    assert Conversation.objects.filter(user=user).count() == 1


# ---------------------------------------------------------------------------
# new_conversation view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_new_conversation_creates_and_redirects(client: Client, user: User) -> None:
    """new_conversation creates a conversation and redirects to it."""
    client.force_login(user)

    response = client.get(reverse("chat:new_conversation"))

    assert response.status_code == 302
    conv = Conversation.objects.filter(user=user).first()
    assert conv is not None
    assert str(conv.id) in response["Location"]


# ---------------------------------------------------------------------------
# conversation view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_conversation_view_renders(client: Client, user: User, conversation: Conversation) -> None:
    """conversation view renders an existing conversation."""
    client.force_login(user)

    response = client.get(reverse("chat:conversation", kwargs={"conversation_id": conversation.id}))

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# load_more view
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_load_more_returns_empty(client: Client, user: User) -> None:
    """load_more returns an empty body."""
    client.force_login(user)

    response = client.post(reverse("chat:load_more"))

    assert response.status_code == 200
    assert response.content == b""


# ---------------------------------------------------------------------------
# send_message view branches
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_send_message_blank_message_returns_400(client: Client, user: User) -> None:
    """A blank message is rejected with 400."""
    client.force_login(user)

    response = client.post(reverse("chat:send_message"), {"message": "   "})

    assert response.status_code == 400


@pytest.mark.django_db
@patch("apps.chat.views._process_chat")
def test_send_message_success_with_products_no_title(
    mock_process: MagicMock,
    client: Client,
    user: User,
    conversation: Conversation,
) -> None:
    """Valid conversation, explicit marketplaces, products and no generated title."""
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
        "search_intent": {"query": "laptop"},
    }

    client.force_login(user)
    response = client.post(
        reverse("chat:send_message"),
        {
            "message": "Busco un laptop",
            "conversation_id": str(conversation.id),
            "marketplaces": "EBAY_US,MLC",
            "destination_country": "CL",
        },
    )

    assert response.status_code == 200
    assert "Gaming Laptop RTX 4060" in response.content.decode()


@pytest.mark.django_db
@patch("apps.chat.views._process_chat")
def test_send_message_sets_generated_title(
    mock_process: MagicMock,
    client: Client,
    user: User,
    conversation: Conversation,
) -> None:
    """A generated title is persisted onto the conversation."""
    mock_process.return_value = {
        "message": "Hi",
        "products": [],
        "has_more": False,
        "generated_title": "Generated Title",
    }

    client.force_login(user)
    response = client.post(
        reverse("chat:send_message"),
        {
            "message": "Busco algo",
            "conversation_id": str(conversation.id),
            "marketplaces": "MLC",
        },
    )

    assert response.status_code == 200
    conversation.refresh_from_db()
    assert conversation.title == "Generated Title"


@pytest.mark.django_db
@patch("apps.chat.views._process_chat")
def test_send_message_creates_conversation_when_no_id(
    mock_process: MagicMock,
    client: Client,
    user: User,
) -> None:
    """A new conversation is created when no id is provided."""
    mock_process.return_value = {
        "message": "Hi",
        "products": [],
        "has_more": False,
    }

    client.force_login(user)
    response = client.post(
        reverse("chat:send_message"),
        {"message": "Busco un laptop", "marketplaces": "MLC"},
    )

    assert response.status_code == 200
    assert Conversation.objects.filter(user=user).count() == 1


@pytest.mark.django_db
@patch("apps.chat.views._process_chat")
def test_send_message_creates_conversation_when_id_invalid(
    mock_process: MagicMock,
    client: Client,
    user: User,
) -> None:
    """An invalid conversation id falls back to creating a new conversation."""
    mock_process.return_value = {
        "message": "Hi",
        "products": [],
        "has_more": False,
    }

    client.force_login(user)
    response = client.post(
        reverse("chat:send_message"),
        {
            "message": "Busco un laptop",
            "conversation_id": "not-a-valid-uuid",
            "marketplaces": "MLC",
        },
    )

    assert response.status_code == 200
    assert Conversation.objects.filter(user=user).count() == 1


@pytest.mark.django_db
@patch("apps.chat.views._process_chat")
def test_send_message_uses_default_marketplaces(
    mock_process: MagicMock,
    client: Client,
    user: User,
    conversation: Conversation,
) -> None:
    """Missing marketplaces fall back to the defaults."""
    mock_process.return_value = {
        "message": "Hi",
        "products": [],
        "has_more": False,
    }

    client.force_login(user)
    client.post(
        reverse("chat:send_message"),
        {"message": "Busco un laptop", "conversation_id": str(conversation.id)},
    )

    call_kwargs = mock_process.call_args.kwargs
    assert "EBAY_US" in call_kwargs["marketplaces"]
    assert "MLC" in call_kwargs["marketplaces"]


@pytest.mark.django_db
@patch("apps.chat.views._process_chat")
def test_send_message_renders_error_on_exception(
    mock_process: MagicMock,
    client: Client,
    user: User,
    conversation: Conversation,
) -> None:
    """Errors are caught and rendered as a localized error message."""
    mock_process.side_effect = RuntimeError("boom")

    client.force_login(user)
    response = client.post(
        reverse("chat:send_message"),
        {
            "message": "Hola, busco un laptop",
            "conversation_id": str(conversation.id),
            "marketplaces": "MLC",
        },
    )

    assert response.status_code == 200
    assert "Lo siento" in response.content.decode()


# ---------------------------------------------------------------------------
# _create_marketplace_factory
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_create_marketplace_factory_registers_active_adapters() -> None:
    """Factory registers eBay and MercadoLibre adapters and skips others."""
    Marketplace.objects.create(
        code="EBAY_US",
        name="eBay US",
        provider=Marketplace.Provider.EBAY,
        country_code="US",
        country_name="United States",
    )
    Marketplace.objects.create(
        code="MLC",
        name="MercadoLibre Chile",
        provider=Marketplace.Provider.MERCADOLIBRE,
        country_code="CL",
        country_name="Chile",
        api_site_id="MLC",
    )
    # A provider that is neither eBay nor MercadoLibre exercises the fall-through
    # branch of the if/elif and must not register an adapter.
    Marketplace.objects.create(
        code="OTHER",
        name="Other Marketplace",
        provider="unknown",
        country_code="XX",
        country_name="Nowhere",
    )

    config = MagicMock()
    config.ebay.app_id = "test-app-id"
    config.ebay.cert_id.get_secret_value.return_value = "test-cert-secret"
    config.mercadolibre.is_configured = True
    config.mercadolibre.app_id = "test-meli-app"
    config.mercadolibre.client_secret.get_secret_value.return_value = "test-meli-secret"

    factory = _create_marketplace_factory(config)

    assert factory.adapter_count == 2
    assert set(factory.registered_codes) == {"EBAY_US", "MLC"}
