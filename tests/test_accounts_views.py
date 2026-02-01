"""Tests for accounts app views."""

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
class TestRegisterView:
    """Tests for register view."""

    def test_register_page_renders(self, client: Client) -> None:
        """Register page renders successfully."""
        response = client.get(reverse("accounts:register"))

        assert response.status_code == 200
        assert b"Create Account" in response.content

    def test_register_success(self, client: Client) -> None:
        """User can register successfully."""
        from apps.accounts.models import User

        response = client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "new@example.com",
                "password1": "ComplexPass123!",
                "password2": "ComplexPass123!",
            },
        )

        assert response.status_code == 302
        assert User.objects.filter(username="newuser").exists()

    def test_register_invalid_data(self, client: Client) -> None:
        """Register shows errors for invalid data."""
        response = client.post(
            reverse("accounts:register"),
            {
                "username": "newuser",
                "email": "invalid-email",
                "password1": "pass",
                "password2": "different",
            },
        )

        assert response.status_code == 200  # Re-renders form with errors

    def test_register_redirects_authenticated(self, client: Client, user: User) -> None:
        """Authenticated users are redirected from register page."""
        client.force_login(user)
        response = client.get(reverse("accounts:register"))

        assert response.status_code == 302


@pytest.mark.django_db
class TestLoginView:
    """Tests for login view."""

    def test_login_page_renders(self, client: Client) -> None:
        """Login page renders successfully."""
        response = client.get(reverse("accounts:login"))

        assert response.status_code == 200
        assert b"Login" in response.content

    def test_login_success(self, client: Client, user: User) -> None:
        """User can login successfully."""
        response = client.post(
            reverse("accounts:login"),
            {
                "username": "testuser",
                "password": "testpass123",
            },
        )

        assert response.status_code == 302

    def test_login_invalid_credentials(self, client: Client, user: User) -> None:
        """Login shows error for invalid credentials."""
        response = client.post(
            reverse("accounts:login"),
            {
                "username": "testuser",
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 200  # Re-renders form with errors

    def test_login_redirects_authenticated(self, client: Client, user: User) -> None:
        """Authenticated users are redirected from login page."""
        client.force_login(user)
        response = client.get(reverse("accounts:login"))

        assert response.status_code == 302


@pytest.mark.django_db
class TestLogoutView:
    """Tests for logout view."""

    def test_logout_success(self, client: Client, user: User) -> None:
        """User can logout successfully."""
        client.force_login(user)
        response = client.get(reverse("accounts:logout"))

        assert response.status_code == 302

    def test_logout_requires_login(self, client: Client) -> None:
        """Logout requires authentication."""
        response = client.get(reverse("accounts:logout"))

        assert response.status_code == 302
        assert "login" in response["Location"]


@pytest.mark.django_db
class TestProfileView:
    """Tests for profile view."""

    def test_profile_renders(self, client: Client, user: User) -> None:
        """Profile page renders for authenticated user."""
        client.force_login(user)
        response = client.get(reverse("accounts:profile"))

        assert response.status_code == 200
        assert b"testuser" in response.content

    def test_profile_requires_login(self, client: Client) -> None:
        """Profile requires authentication."""
        response = client.get(reverse("accounts:profile"))

        assert response.status_code == 302
        assert "login" in response["Location"]
