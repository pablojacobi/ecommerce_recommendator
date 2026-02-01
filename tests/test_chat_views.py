"""Tests for chat app views."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.test import Client
from django.urls import reverse

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
        assert b"Product Recommendations" in response.content

    def test_index_requires_login(self, client: Client) -> None:
        """Chat index requires authentication."""
        response = client.get(reverse("chat:index"))

        assert response.status_code == 302
        assert "login" in response["Location"]
