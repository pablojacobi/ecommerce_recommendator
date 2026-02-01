"""Tests for Django models."""

import pytest

from apps.accounts.models import User


@pytest.mark.django_db
class TestUserModel:
    """Tests for the User model."""

    def test_user_str_returns_username(self) -> None:
        """User __str__ should return the username."""
        user = User(username="testuser", email="test@example.com")

        assert str(user) == "testuser"

    def test_user_preferred_marketplaces_default_empty_list(self) -> None:
        """User preferred_marketplaces should default to empty list."""
        user = User(username="testuser")

        assert user.preferred_marketplaces == []

    def test_user_preferred_marketplaces_can_be_set(self) -> None:
        """User preferred_marketplaces can store marketplace IDs."""
        user = User(username="testuser")
        user.preferred_marketplaces = ["EBAY_US", "MLC"]

        assert user.preferred_marketplaces == ["EBAY_US", "MLC"]
