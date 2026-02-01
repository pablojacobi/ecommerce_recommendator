"""Tests for Gemini AI service."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.result import Failure, Success
from services.gemini.service import GeminiError, GeminiService
from services.gemini.types import (
    ConversationContext,
    IntentType,
    SearchIntent,
)
from services.marketplaces.base import SortOrder


class TestGeminiError:
    """Tests for GeminiError exception."""

    def test_create_with_message(self) -> None:
        """GeminiError can be created with message."""
        error = GeminiError("Test error")

        assert error.message == "Test error"
        assert error.details is None
        assert str(error) == "Test error"

    def test_create_with_details(self) -> None:
        """GeminiError can be created with details."""
        error = GeminiError("Test error", details="More info")

        assert error.message == "Test error"
        assert error.details == "More info"


class TestGeminiServiceInit:
    """Tests for GeminiService initialization."""

    def test_init_with_valid_key(self) -> None:
        """GeminiService can be initialized with valid key."""
        service = GeminiService(api_key="test-key")

        assert service._api_key == "test-key"
        assert service._model == "gemini-2.0-flash"
        assert service._client is None

    def test_init_with_custom_model(self) -> None:
        """GeminiService can be initialized with custom model."""
        service = GeminiService(api_key="test-key", model="gemini-pro")

        assert service._model == "gemini-pro"

    def test_init_with_empty_key_raises(self) -> None:
        """GeminiService should raise ValueError for empty key."""
        with pytest.raises(ValueError, match="API key is required"):
            GeminiService(api_key="")


class TestGeminiServiceExtractSearchIntent:
    """Tests for extract_search_intent method."""

    @pytest.fixture()
    def service(self) -> GeminiService:
        """Create a service for testing."""
        return GeminiService(api_key="test-key")

    @pytest.fixture()
    def mock_response(self) -> MagicMock:
        """Create a mock Gemini response."""
        response = MagicMock()
        response.text = """{
            "query": "laptop gaming",
            "sort_order": "price_asc",
            "min_price": 500,
            "max_price": 1000,
            "require_free_shipping": true,
            "min_seller_rating": 4.0,
            "condition": "new",
            "destination_country": "CL",
            "include_import_taxes": true,
            "limit": 30,
            "keywords": ["gaming", "rgb"]
        }"""
        return response

    @pytest.mark.asyncio
    async def test_extract_search_intent_success(
        self,
        service: GeminiService,
        mock_response: MagicMock,
    ) -> None:
        """extract_search_intent should return SearchIntent on success."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_search_intent("laptop gaming barata")

        assert isinstance(result, Success)
        intent = result.value
        assert intent.query == "laptop gaming"
        assert intent.sort_order == SortOrder.PRICE_ASC
        assert intent.min_price == Decimal("500")
        assert intent.max_price == Decimal("1000")
        assert intent.require_free_shipping is True
        assert intent.min_seller_rating == 4.0
        assert intent.condition == "new"
        assert intent.destination_country == "CL"
        assert intent.include_import_taxes is True
        assert intent.limit == 30
        assert intent.keywords == ("gaming", "rgb")

    @pytest.mark.asyncio
    async def test_extract_search_intent_empty_query(
        self,
        service: GeminiService,
    ) -> None:
        """extract_search_intent should fail for empty query."""
        result = await service.extract_search_intent("")

        assert isinstance(result, Failure)
        assert "cannot be empty" in result.error.message

    @pytest.mark.asyncio
    async def test_extract_search_intent_whitespace_query(
        self,
        service: GeminiService,
    ) -> None:
        """extract_search_intent should fail for whitespace-only query."""
        result = await service.extract_search_intent("   ")

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_extract_search_intent_empty_response(
        self,
        service: GeminiService,
    ) -> None:
        """extract_search_intent should fail for empty AI response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_search_intent("laptop")

        assert isinstance(result, Failure)
        assert "Empty response" in result.error.message

    @pytest.mark.asyncio
    async def test_extract_search_intent_invalid_json(
        self,
        service: GeminiService,
    ) -> None:
        """extract_search_intent should fail for invalid JSON response."""
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_search_intent("laptop")

        assert isinstance(result, Failure)
        assert "Invalid JSON" in result.error.message

    @pytest.mark.asyncio
    async def test_extract_search_intent_api_error(
        self,
        service: GeminiService,
    ) -> None:
        """extract_search_intent should fail on API error."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_search_intent("laptop")

        assert isinstance(result, Failure)
        assert "Failed to process" in result.error.message

    @pytest.mark.asyncio
    async def test_extract_search_intent_json_with_markdown(
        self,
        service: GeminiService,
    ) -> None:
        """extract_search_intent should handle JSON wrapped in markdown."""
        mock_response = MagicMock()
        mock_response.text = """```json
        {
            "query": "laptop",
            "sort_order": null,
            "min_price": null,
            "max_price": null,
            "require_free_shipping": false,
            "min_seller_rating": null,
            "condition": null,
            "destination_country": null,
            "include_import_taxes": false,
            "limit": 20,
            "keywords": []
        }
        ```"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_search_intent("laptop")

        assert isinstance(result, Success)
        assert result.value.query == "laptop"


class TestGeminiServiceExtractRefinementIntent:
    """Tests for extract_refinement_intent method."""

    @pytest.fixture()
    def service(self) -> GeminiService:
        """Create a service for testing."""
        return GeminiService(api_key="test-key")

    @pytest.fixture()
    def context(self) -> ConversationContext:
        """Create a conversation context."""
        ctx = ConversationContext()
        ctx.last_search_intent = SearchIntent(
            query="laptop",
            original_query="find me a laptop",
        )
        ctx.last_results_count = 50
        return ctx

    @pytest.mark.asyncio
    async def test_extract_refinement_intent_success(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """extract_refinement_intent should return RefinementIntent."""
        mock_response = MagicMock()
        mock_response.text = """{
            "refinement_type": "cheapest",
            "filter_criteria": {},
            "sort_preference": "price_asc",
            "comparison_criteria": null,
            "requires_new_search": false
        }"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_refinement_intent("dame el más barato", context)

        assert isinstance(result, Success)
        intent = result.value
        assert intent.refinement_type == "cheapest"
        assert intent.sort_preference == "price_asc"

    @pytest.mark.asyncio
    async def test_extract_refinement_intent_empty_query(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """extract_refinement_intent should fail for empty query."""
        result = await service.extract_refinement_intent("", context)

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_extract_refinement_intent_no_previous_search(
        self,
        service: GeminiService,
    ) -> None:
        """extract_refinement_intent should work without previous search."""
        context = ConversationContext()
        mock_response = MagicMock()
        mock_response.text = """{
            "refinement_type": "filter",
            "filter_criteria": {"condition": "new"},
            "sort_preference": null,
            "comparison_criteria": null,
            "requires_new_search": false
        }"""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_refinement_intent("solo nuevos", context)

        assert isinstance(result, Success)

    @pytest.mark.asyncio
    async def test_extract_refinement_intent_empty_response(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """extract_refinement_intent should fail for empty response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_refinement_intent("test", context)

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_extract_refinement_intent_api_error(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """extract_refinement_intent should fail on API error."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_refinement_intent("test", context)

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_extract_refinement_intent_invalid_json(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """extract_refinement_intent should fail for invalid JSON."""
        mock_response = MagicMock()
        mock_response.text = "not valid json"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.extract_refinement_intent("test", context)

        assert isinstance(result, Failure)
        assert "Invalid JSON" in result.error.message


class TestGeminiServiceClassifyIntent:
    """Tests for classify_intent method."""

    @pytest.fixture()
    def service(self) -> GeminiService:
        """Create a service for testing."""
        return GeminiService(api_key="test-key")

    @pytest.fixture()
    def context(self) -> ConversationContext:
        """Create a conversation context."""
        return ConversationContext()

    @pytest.mark.asyncio
    async def test_classify_intent_search(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should identify search intent."""
        mock_response = MagicMock()
        mock_response.text = '{"intent_type": "search", "confidence": 0.95}'
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.classify_intent("find me a laptop", context)

        assert isinstance(result, Success)
        assert result.value == IntentType.SEARCH

    @pytest.mark.asyncio
    async def test_classify_intent_refinement(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should identify refinement intent."""
        mock_response = MagicMock()
        mock_response.text = '{"intent_type": "refinement", "confidence": 0.9}'
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.classify_intent("show me cheaper ones", context)

        assert isinstance(result, Success)
        assert result.value == IntentType.REFINEMENT

    @pytest.mark.asyncio
    async def test_classify_intent_empty_message(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should fail for empty message."""
        result = await service.classify_intent("", context)

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_classify_intent_empty_response(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should fail for empty AI response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.classify_intent("test", context)

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_classify_intent_invalid_type_defaults_to_search(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should default to search for invalid type."""
        mock_response = MagicMock()
        mock_response.text = '{"intent_type": "invalid", "confidence": 0.5}'
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.classify_intent("test", context)

        assert isinstance(result, Success)
        assert result.value == IntentType.SEARCH

    @pytest.mark.asyncio
    async def test_classify_intent_api_error(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should fail on API error."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.classify_intent("test", context)

        assert isinstance(result, Failure)

    @pytest.mark.asyncio
    async def test_classify_intent_invalid_json(
        self,
        service: GeminiService,
        context: ConversationContext,
    ) -> None:
        """classify_intent should fail for invalid JSON."""
        mock_response = MagicMock()
        mock_response.text = "not valid json at all"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.classify_intent("test", context)

        assert isinstance(result, Failure)
        assert "Invalid JSON" in result.error.message


class TestGeminiServiceHealthcheck:
    """Tests for healthcheck method."""

    @pytest.fixture()
    def service(self) -> GeminiService:
        """Create a service for testing."""
        return GeminiService(api_key="test-key")

    @pytest.mark.asyncio
    async def test_healthcheck_success(self, service: GeminiService) -> None:
        """healthcheck should return True when API is available."""
        mock_response = MagicMock()
        mock_response.text = "ok"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.healthcheck()

        assert result is True

    @pytest.mark.asyncio
    async def test_healthcheck_failure(self, service: GeminiService) -> None:
        """healthcheck should return False when API fails."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("API Error")

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.healthcheck()

        assert result is False

    @pytest.mark.asyncio
    async def test_healthcheck_empty_response(self, service: GeminiService) -> None:
        """healthcheck should return False for empty response."""
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch.object(service, "_get_client", return_value=mock_client):
            result = await service.healthcheck()

        assert result is False


class TestGeminiServiceHelpers:
    """Tests for helper methods."""

    @pytest.fixture()
    def service(self) -> GeminiService:
        """Create a service for testing."""
        return GeminiService(api_key="test-key")

    def test_parse_json_response_valid(self, service: GeminiService) -> None:
        """_parse_json_response should parse valid JSON."""
        result = service._parse_json_response('{"key": "value"}')

        assert isinstance(result, Success)
        assert result.value == {"key": "value"}

    def test_parse_json_response_with_markdown(self, service: GeminiService) -> None:
        """_parse_json_response should handle markdown code blocks."""
        result = service._parse_json_response('```json\n{"key": "value"}\n```')

        assert isinstance(result, Success)
        assert result.value == {"key": "value"}

    def test_parse_json_response_with_triple_backticks(self, service: GeminiService) -> None:
        """_parse_json_response should handle triple backticks."""
        result = service._parse_json_response('```\n{"key": "value"}\n```')

        assert isinstance(result, Success)
        assert result.value == {"key": "value"}

    def test_parse_json_response_invalid(self, service: GeminiService) -> None:
        """_parse_json_response should fail for invalid JSON."""
        result = service._parse_json_response("not json")

        assert isinstance(result, Failure)
        assert "Invalid JSON" in result.error.message

    def test_build_search_intent_minimal(self, service: GeminiService) -> None:
        """_build_search_intent should work with minimal data."""
        data: dict[str, Any] = {"query": "laptop"}
        intent = service._build_search_intent(data, "find laptop")

        assert intent.query == "laptop"
        assert intent.original_query == "find laptop"
        assert intent.limit == 20

    def test_build_search_intent_with_sort(self, service: GeminiService) -> None:
        """_build_search_intent should map sort order."""
        data: dict[str, Any] = {"query": "laptop", "sort_order": "price_desc"}
        intent = service._build_search_intent(data, "laptop")

        assert intent.sort_order == SortOrder.PRICE_DESC

    def test_build_search_intent_unknown_sort(self, service: GeminiService) -> None:
        """_build_search_intent should handle unknown sort order."""
        data: dict[str, Any] = {"query": "laptop", "sort_order": "unknown"}
        intent = service._build_search_intent(data, "laptop")

        assert intent.sort_order is None

    def test_build_search_intent_limit_clamped(self, service: GeminiService) -> None:
        """_build_search_intent should clamp limit to valid range."""
        # Test max
        data: dict[str, Any] = {"query": "laptop", "limit": 500}
        intent = service._build_search_intent(data, "laptop")
        assert intent.limit == 100

        # Test min
        data = {"query": "laptop", "limit": 0}
        intent = service._build_search_intent(data, "laptop")
        assert intent.limit == 1

    def test_build_context_summary_no_previous(self, service: GeminiService) -> None:
        """_build_context_summary should handle no previous search."""
        context = ConversationContext()
        summary = service._build_context_summary(context)

        assert summary == "No previous search"

    def test_build_context_summary_with_previous(self, service: GeminiService) -> None:
        """_build_context_summary should include previous search info."""
        context = ConversationContext()
        context.last_search_intent = SearchIntent(
            query="laptop",
            original_query="find laptop",
        )
        context.last_results_count = 25

        summary = service._build_context_summary(context)

        assert "find laptop" in summary
        assert "25 results" in summary


class TestGeminiServiceGetClient:
    """Tests for _get_client method."""

    def test_get_client_creates_client(self) -> None:
        """_get_client should create client on first call."""
        service = GeminiService(api_key="test-key")

        with patch("google.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client_class.return_value = mock_client

            client = service._get_client()

            assert client == mock_client
            mock_client_class.assert_called_once_with(api_key="test-key")

    def test_get_client_reuses_client(self) -> None:
        """_get_client should reuse existing client."""
        service = GeminiService(api_key="test-key")
        mock_client = MagicMock()
        service._client = mock_client

        client = service._get_client()

        assert client == mock_client
