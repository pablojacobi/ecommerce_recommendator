"""Tests for chat service."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.result import failure, success
from services.chat.service import ChatService, ChatServiceError
from services.chat.types import ChatRequest, ChatResponse
from services.gemini.service import GeminiError
from services.gemini.types import (
    IntentType,
    RefinementIntent,
    SearchIntent,
)
from services.marketplaces.base import ProductResult, SortOrder
from services.marketplaces.errors import ErrorCode, MarketplaceError
from services.search.types import AggregatedResult, EnrichedProduct, MarketplaceSearchResult


@pytest.fixture()
def mock_gemini() -> MagicMock:
    """Create a mock GeminiService."""
    return MagicMock()


@pytest.fixture()
def mock_search() -> MagicMock:
    """Create a mock SearchOrchestrator."""
    return MagicMock()


@pytest.fixture()
def chat_service(mock_gemini: MagicMock, mock_search: MagicMock) -> ChatService:
    """Create a ChatService with mocked dependencies."""
    return ChatService(
        gemini_service=mock_gemini,
        search_orchestrator=mock_search,
    )


@pytest.fixture()
def sample_request() -> ChatRequest:
    """Create a sample chat request."""
    return ChatRequest(
        content="Busco un laptop gaming barato",
        conversation_id="conv-123",
        user_id="user-456",
        marketplace_codes=("MLC", "EBAY_US"),
        conversation_history=(
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "Hola! ¿En qué puedo ayudarte?"},
        ),
    )


@pytest.fixture()
def sample_search_intent() -> SearchIntent:
    """Create a sample search intent."""
    return SearchIntent(
        query="laptop gaming",
        original_query="Busco un laptop gaming barato",
        sort_order=SortOrder.PRICE_ASC,
        limit=20,
    )


@pytest.fixture()
def sample_product() -> ProductResult:
    """Create a sample product result."""
    return ProductResult(
        id="prod-123",
        marketplace_code="EBAY_US",
        title="Gaming Laptop RTX 4060",
        price=Decimal("999.99"),
        currency="USD",
        url="https://example.com/laptop",
        image_url="https://example.com/laptop.jpg",
        seller_name="TechStore",
        seller_rating=4.5,
        condition="new",
        shipping_cost=Decimal("0"),
        free_shipping=True,
    )


@pytest.fixture()
def sample_aggregated_result(sample_product: ProductResult) -> AggregatedResult:
    """Create a sample aggregated result."""
    enriched = EnrichedProduct(
        product=sample_product,
        marketplace_code="EBAY_US",
        marketplace_name="eBay United States",
        is_best_price=True,
        price_rank=1,
    )
    return AggregatedResult(
        products=[enriched],
        marketplace_results=[
            MarketplaceSearchResult(
                marketplace_code="EBAY_US",
                marketplace_name="eBay United States",
                products=[enriched],
                total_count=100,
                has_more=True,
            ),
        ],
        total_count=100,
        sort_order=SortOrder.PRICE_ASC,
        query="laptop gaming",
        has_more=True,
    )


class TestChatServiceError:
    """Tests for ChatServiceError."""

    def test_error_message(self) -> None:
        """ChatServiceError should store message."""
        error = ChatServiceError("Something went wrong")
        assert str(error) == "Something went wrong"


class TestChatServiceInit:
    """Tests for ChatService initialization."""

    def test_init(self, mock_gemini: MagicMock, mock_search: MagicMock) -> None:
        """ChatService should initialize with dependencies."""
        service = ChatService(
            gemini_service=mock_gemini,
            search_orchestrator=mock_search,
        )
        assert service._gemini is mock_gemini
        assert service._search is mock_search


class TestChatServiceProcess:
    """Tests for ChatService.process method."""

    @pytest.mark.asyncio()
    async def test_process_search_success(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Process should handle search intent successfully."""
        # Setup mocks
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        # Execute
        response = await chat_service.process(sample_request)

        # Verify
        assert response.is_success
        assert response.intent_type == IntentType.SEARCH
        assert response.search_intent == sample_search_intent
        assert response.search_results == sample_aggregated_result
        assert "laptop gaming" in response.message

    @pytest.mark.asyncio()
    async def test_process_classify_intent_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        sample_request: ChatRequest,
    ) -> None:
        """Process should handle intent classification failure."""
        mock_gemini.classify_intent = AsyncMock(return_value=failure(GeminiError("API error")))

        response = await chat_service.process(sample_request)

        assert not response.is_success
        assert "reformularla" in response.message

    @pytest.mark.asyncio()
    async def test_process_extract_intent_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        sample_request: ChatRequest,
    ) -> None:
        """Process should handle search intent extraction failure."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(
            return_value=failure(GeminiError("Parse error"))
        )

        response = await chat_service.process(sample_request)

        assert not response.is_success
        assert "específico" in response.message

    @pytest.mark.asyncio()
    async def test_process_search_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Process should handle search failure."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(
            return_value=failure(
                MarketplaceError(
                    code=ErrorCode.NETWORK,
                    message="Network error",
                    marketplace_code="EBAY_US",
                )
            )
        )

        response = await chat_service.process(sample_request)

        assert not response.is_success
        assert "intenta de nuevo" in response.message

    @pytest.mark.asyncio()
    async def test_process_no_marketplaces(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Process should prompt for marketplace selection."""
        request = ChatRequest(
            content="Busco laptop",
            conversation_id="conv-123",
            user_id="user-456",
            marketplace_codes=(),  # No marketplaces
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))

        response = await chat_service.process(request)

        assert response.is_success
        assert "selecciona" in response.message.lower()
        assert response.search_results is None

    @pytest.mark.asyncio()
    async def test_process_exception(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        sample_request: ChatRequest,
    ) -> None:
        """Process should handle unexpected exceptions."""
        mock_gemini.classify_intent = AsyncMock(side_effect=RuntimeError("Unexpected error"))

        response = await chat_service.process(sample_request)

        assert not response.is_success
        assert "error" in response.message.lower()


class TestChatServiceIntents:
    """Tests for intent handling."""

    @pytest.mark.asyncio()
    async def test_handle_refinement(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Process should handle refinement intent."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(
                    refinement_type="filter",
                    original_query="De esos, el más barato",
                )
            )
        )
        # Falls back to search
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        response = await chat_service.process(sample_request)

        assert response.is_success
        mock_gemini.extract_refinement_intent.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_refinement_failure_fallback(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Refinement failure should fall back to search."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=failure(GeminiError("Parse error"))
        )
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        response = await chat_service.process(sample_request)

        assert response.is_success
        # Should have fallen back to search
        mock_gemini.extract_search_intent.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_more_results_without_context(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
    ) -> None:
        """More results without previous search should ask for search."""
        request = ChatRequest(
            content="Dame más",
            conversation_id="conv-123",
            user_id="user-456",
            marketplace_codes=("MLC",),
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.MORE_RESULTS))

        response = await chat_service.process(request)

        assert response.is_success
        assert "búsqueda previa" in response.message.lower()

    @pytest.mark.asyncio()
    async def test_handle_more_results_with_previous_search(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """More results with previous search should re-execute search."""
        from unittest.mock import patch

        from services.gemini.types import ConversationContext

        request = ChatRequest(
            content="Dame más resultados",
            conversation_id="conv-123",
            user_id="user-456",
            marketplace_codes=("MLC",),
        )

        # Create context with previous search intent
        context_with_intent = ConversationContext(
            selected_marketplaces=["MLC"],
            last_search_intent=sample_search_intent,
        )

        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.MORE_RESULTS))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        # Patch _build_context to return context with last_search_intent
        with patch.object(
            chat_service,
            "_build_context",
            return_value=context_with_intent,
        ):
            response = await chat_service.process(request)

        assert response.is_success
        # Should have executed search
        mock_gemini.extract_search_intent.assert_called_once()

    @pytest.mark.asyncio()
    async def test_handle_clarification(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        sample_request: ChatRequest,
    ) -> None:
        """Process should handle clarification intent."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.CLARIFICATION))

        response = await chat_service.process(sample_request)

        assert response.is_success
        assert response.intent_type == IntentType.CLARIFICATION
        assert "ayudarte" in response.message.lower()

    @pytest.mark.asyncio()
    async def test_handle_comparison_fallback_to_search(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Comparison intent should fall back to search."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.COMPARISON))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        response = await chat_service.process(sample_request)

        assert response.is_success
        # Should have fallen back to search
        mock_gemini.extract_search_intent.assert_called_once()


class TestChatServiceResponseFormatting:
    """Tests for response formatting."""

    @pytest.mark.asyncio()
    async def test_format_no_results(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Should format message for no results."""
        empty_result = AggregatedResult(
            products=[],
            marketplace_results=[],
            total_count=0,
            query="unicornio volador",
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(empty_result))

        response = await chat_service.process(sample_request)

        assert response.is_success
        assert "no encontré" in response.message.lower()

    @pytest.mark.asyncio()
    async def test_format_with_failed_marketplaces(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Should mention failed marketplaces."""
        result_with_failures = AggregatedResult(
            products=[],
            marketplace_results=[
                MarketplaceSearchResult(
                    marketplace_code="MLC",
                    marketplace_name="MercadoLibre Chile",
                    error="Connection timeout",
                ),
            ],
            total_count=0,
            query="laptop",
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(result_with_failures))

        response = await chat_service.process(sample_request)

        assert "problemas" in response.message.lower()
        assert "MLC" in response.message

    @pytest.mark.asyncio()
    async def test_format_with_has_more(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Should mention more results available."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        response = await chat_service.process(sample_request)

        assert "más resultados" in response.message.lower()

    @pytest.mark.asyncio()
    async def test_format_results_no_has_more(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_request: ChatRequest,
        sample_search_intent: SearchIntent,
        sample_product: ProductResult,
    ) -> None:
        """Should not mention more results when has_more=False."""
        enriched = EnrichedProduct(
            product=sample_product,
            marketplace_code="EBAY_US",
            marketplace_name="eBay US",
            is_best_price=False,
            price_rank=1,
        )
        result = AggregatedResult(
            products=[enriched],
            marketplace_results=[],
            total_count=1,
            query="laptop",
            has_more=False,
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(result))

        response = await chat_service.process(sample_request)

        assert response.is_success
        assert "más resultados" not in response.message.lower()

    @pytest.mark.asyncio()
    async def test_build_context_user_only_messages(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Should handle conversation with only user messages."""
        request = ChatRequest(
            content="Find laptop",
            conversation_id="conv-123",
            user_id="user-456",
            marketplace_codes=("MLC",),
            conversation_history=({"role": "user", "content": "Previous query"},),
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        response = await chat_service.process(request)

        assert response.is_success

    @pytest.mark.asyncio()
    async def test_build_context_ignores_unknown_roles(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
        sample_aggregated_result: AggregatedResult,
    ) -> None:
        """Should ignore messages with unknown roles."""
        request = ChatRequest(
            content="Find laptop",
            conversation_id="conv-123",
            user_id="user-456",
            marketplace_codes=("MLC",),
            conversation_history=(
                {"role": "system", "content": "System message"},  # Unknown role
                {"role": "user", "content": "User message"},
            ),
        )
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(sample_aggregated_result))

        response = await chat_service.process(request)

        assert response.is_success


class TestChatServiceClose:
    """Tests for ChatService.close method."""

    @pytest.mark.asyncio()
    async def test_close(
        self,
        chat_service: ChatService,
        mock_search: MagicMock,
    ) -> None:
        """Close should close search orchestrator."""
        mock_search.close = AsyncMock()

        await chat_service.close()

        mock_search.close.assert_called_once()


class TestChatTypes:
    """Tests for chat types."""

    def test_chat_request_defaults(self) -> None:
        """ChatRequest should have sensible defaults."""
        request = ChatRequest(
            content="Test",
            conversation_id="123",
            user_id="456",
        )
        assert request.marketplace_codes == ()
        assert request.conversation_history == ()

    def test_chat_response_is_success(self) -> None:
        """ChatResponse.is_success should return True when no error."""
        response = ChatResponse(message="Success")
        assert response.is_success

        response_with_error = ChatResponse(message="Error", error="Something failed")
        assert not response_with_error.is_success

    def test_chat_response_has_results(self, sample_aggregated_result: AggregatedResult) -> None:
        """ChatResponse.has_results should return True when results exist."""
        response_no_results = ChatResponse(message="No results")
        assert not response_no_results.has_results

        response_with_results = ChatResponse(
            message="Found results",
            search_results=sample_aggregated_result,
        )
        assert response_with_results.has_results

        empty_results = AggregatedResult(products=[], query="test")
        response_empty = ChatResponse(
            message="Empty results",
            search_results=empty_results,
        )
        assert not response_empty.has_results
