"""Branch-coverage tests for the Gemini AI service.

These tests target the uncovered branches in ``services/gemini/service.py``:
- ``_build_search_intent`` sort-criteria handling (old ``secondary_sort_order``
  path and the new ``sort_criteria`` array format).
- ``generate_title`` (empty message, success, empty/blank AI text, error fallback).
- ``generate_response`` (success, empty AI text fallback, error fallback).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from services.gemini.service import GeminiService
from services.marketplaces.base import SortOrder


@pytest.fixture()
def service() -> GeminiService:
    """Create a service for testing."""
    return GeminiService(api_key="test-key")


class TestBuildSearchIntentSortCriteria:
    """Tests for the sort-criteria branches of ``_build_search_intent``."""

    def test_old_format_with_secondary_sort_order(self, service: GeminiService) -> None:
        """Old format should append a valid secondary sort order."""
        data: dict[str, Any] = {
            "query": "laptop",
            "sort_order": "price_asc",
            "secondary_sort_order": "newest",
        }
        intent = service._build_search_intent(data, "laptop")

        assert intent.sort_criteria == (SortOrder.PRICE_ASC, SortOrder.NEWEST)

    def test_old_format_with_unknown_secondary_sort_order(self, service: GeminiService) -> None:
        """Old format should ignore an unknown secondary sort order."""
        data: dict[str, Any] = {
            "query": "laptop",
            "sort_order": "price_asc",
            "secondary_sort_order": "bogus",
        }
        intent = service._build_search_intent(data, "laptop")

        assert intent.sort_criteria == (SortOrder.PRICE_ASC,)

    def test_new_format_sort_criteria_array(self, service: GeminiService) -> None:
        """New format should map each valid entry of the sort_criteria array."""
        data: dict[str, Any] = {
            "query": "laptop",
            "sort_criteria": ["price_desc", "best_seller"],
        }
        intent = service._build_search_intent(data, "laptop")

        assert intent.sort_criteria == (SortOrder.PRICE_DESC, SortOrder.BEST_SELLER)

    def test_new_format_ignores_invalid_and_empty_entries(self, service: GeminiService) -> None:
        """New format should skip falsy or unknown entries in the array."""
        data: dict[str, Any] = {
            "query": "laptop",
            "sort_criteria": ["price_asc", "", "unknown", "newest"],
        }
        intent = service._build_search_intent(data, "laptop")

        assert intent.sort_criteria == (SortOrder.PRICE_ASC, SortOrder.NEWEST)


class TestGenerateTitle:
    """Tests for the ``generate_title`` method."""

    async def test_empty_message_returns_default(self, service: GeminiService) -> None:
        """generate_title should return the default title for empty message."""
        result = await service.generate_title("")

        assert result == "New conversation"

    async def test_whitespace_message_returns_default(self, service: GeminiService) -> None:
        """generate_title should return the default title for whitespace message."""
        result = await service.generate_title("   ")

        assert result == "New conversation"

    async def test_success_returns_stripped_title(self, service: GeminiService) -> None:
        """generate_title should return the AI-generated title, stripped and truncated."""
        mock_response = MagicMock()
        mock_response.text = "  Gaming Laptops  "
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_title("find me a gaming laptop")

        assert result == "Gaming Laptops"

    async def test_blank_ai_text_returns_default(self, service: GeminiService) -> None:
        """generate_title should return the default when the AI text is only whitespace."""
        mock_response = MagicMock()
        mock_response.text = "   "
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_title("find me a laptop")

        assert result == "New conversation"

    async def test_empty_ai_text_returns_default(self, service: GeminiService) -> None:
        """generate_title should return the default when the AI text is empty."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_title("find me a laptop")

        assert result == "New conversation"

    async def test_error_short_message_falls_back_to_message(self, service: GeminiService) -> None:
        """On error, a short message should be returned verbatim as the fallback title."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_title("laptop")

        assert result == "laptop"

    async def test_error_long_message_falls_back_to_truncated(self, service: GeminiService) -> None:
        """On error, a long message should be truncated to 30 chars as the fallback title."""
        long_message = "a" * 50
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_title(long_message)

        assert result == "a" * 30


class TestGenerateResponse:
    """Tests for the ``generate_response`` method."""

    async def test_success_returns_stripped_text(self, service: GeminiService) -> None:
        """generate_response should return the AI text, stripped."""
        mock_response = MagicMock()
        mock_response.text = "  Found some great deals!  "
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_response("laptop", count=5, total=10)

        assert result == "Found some great deals!"

    async def test_empty_ai_text_returns_fallback(self, service: GeminiService) -> None:
        """generate_response should return the fallback when the AI text is empty."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_response(
                "laptop",
                count=3,
                total=8,
                best_product="Dell XPS",
                marketplace="eBay",
            )

        assert result == "Found 3 products for 'laptop'."

    async def test_error_returns_fallback(self, service: GeminiService) -> None:
        """generate_response should return the fallback on API error."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.generate_response("laptop", count=7, total=12)

        assert result == "Found 7 products for 'laptop'."
