"""
Pytest configuration and fixtures for the test suite.

This module contains shared fixtures used across all tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.test import Client

if TYPE_CHECKING:
    from apps.accounts.models import User


@pytest.fixture()
def test_client() -> Client:
    """Return a Django test client."""
    return Client()


@pytest.fixture()
def authenticated_client(test_client: Client, user: User) -> Client:
    """Return an authenticated Django test client."""
    test_client.force_login(user)
    return test_client


# User fixture will be added in PR #3 when we implement the full User model
