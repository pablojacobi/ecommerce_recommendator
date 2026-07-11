"""Branch-coverage tests for the chat service.

These tests target the refinement handler, the search-with-context fallback,
the context reconstruction, and every language/formatting variation of the
response formatter so that ``services/chat/service.py`` reaches 100% branch
coverage on its own.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.result import failure, success
from services.chat.service import ChatService
from services.chat.types import ChatRequest
from services.gemini.service import GeminiError
from services.gemini.types import (
    ConversationContext,
    IntentType,
    RefinementIntent,
    SearchIntent,
)
from services.marketplaces.base import ProductResult, SortOrder
from services.marketplaces.errors import ErrorCode, MarketplaceError
from services.search.types import (
    AggregatedResult,
    EnrichedProduct,
    MarketplaceSearchResult,
    TaxInfo,
)

# Content strings whose language is unambiguous for ``_is_spanish`` (which does a
# substring match against Spanish indicator words).
SPANISH_CONTENT = "busco un laptop barato"
ENGLISH_CONTENT = "Find some items"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
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
    return ChatService(gemini_service=mock_gemini, search_orchestrator=mock_search)


@pytest.fixture()
def sample_search_intent() -> SearchIntent:
    """Create a sample search intent."""
    return SearchIntent(
        query="laptop gaming",
        original_query="Busco un laptop gaming barato",
        sort_criteria=(SortOrder.PRICE_ASC,),
        limit=20,
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _product(
    price: str = "999.99",
    title: str = "Gaming Laptop RTX 4060 Super Fast Model X With Long Name",
) -> ProductResult:
    """Build a product result."""
    return ProductResult(
        id="prod-1",
        marketplace_code="EBAY_US",
        title=title,
        price=Decimal(price),
        currency="USD",
        url="https://example.com/prod",
    )


def _tax(*, de_minimis: bool) -> TaxInfo:
    """Build tax info."""
    return TaxInfo(
        product_price_usd=Decimal("1000"),
        shipping_cost_usd=Decimal("0"),
        customs_duty=Decimal("60"),
        vat=Decimal("189.99"),
        total_taxes=Decimal("249.99"),
        total_with_taxes=Decimal("1249.98"),
        destination_country="CL",
        destination_country_name="Chile",
        de_minimis_applied=de_minimis,
    )


def _enriched(
    *,
    is_best_price: bool = True,
    tax_info: TaxInfo | None = None,
) -> EnrichedProduct:
    """Build an enriched product."""
    return EnrichedProduct(
        product=_product(),
        marketplace_code="EBAY_US",
        marketplace_name="eBay United States",
        is_best_price=is_best_price,
        price_rank=1,
        tax_info=tax_info,
    )


def _ok_marketplace(code: str = "EBAY_US") -> MarketplaceSearchResult:
    """Build a successful marketplace result."""
    return MarketplaceSearchResult(
        marketplace_code=code,
        marketplace_name=f"{code} name",
        products=[_enriched()],
        total_count=100,
        has_more=True,
    )


def _failed_marketplace(code: str = "MLC") -> MarketplaceSearchResult:
    """Build a failed marketplace result."""
    return MarketplaceSearchResult(
        marketplace_code=code,
        marketplace_name=f"{code} name",
        error="boom",
    )


def _aggregated(
    *,
    products: list[EnrichedProduct] | None = None,
    marketplace_results: list[MarketplaceSearchResult] | None = None,
    total_count: int = 100,
    has_more: bool = True,
) -> AggregatedResult:
    """Build an aggregated result."""
    return AggregatedResult(
        products=products if products is not None else [_enriched()],
        marketplace_results=marketplace_results
        if marketplace_results is not None
        else [_ok_marketplace()],
        total_count=total_count,
        sort_order=SortOrder.PRICE_ASC,
        query="laptop gaming",
        has_more=has_more,
    )


def _refinement_request(
    *,
    content: str = "De esos, el más barato",
    search_params: dict[str, Any] | None = None,
    extra_history: tuple[dict[str, Any], ...] = (),
    marketplaces: tuple[str, ...] = ("MLC", "EBAY_US"),
) -> ChatRequest:
    """Build a request whose history carries a prior search (for refinement)."""
    history: tuple[dict[str, Any], ...] = (
        {"role": "user", "content": "Busco un laptop gaming"},
        *extra_history,
    )
    if search_params is not None:
        history = (
            *history,
            {
                "role": "assistant",
                "content": "Encontré estos laptops",
                "search_params": search_params,
            },
        )
    return ChatRequest(
        content=content,
        conversation_id="conv-123",
        user_id="user-456",
        marketplace_codes=marketplaces,
        conversation_history=history,
    )


# --------------------------------------------------------------------------- #
# process / dispatch / handle_search core paths
# --------------------------------------------------------------------------- #
class TestProcessAndDispatch:
    """Cover the top-level process flow and intent dispatch."""

    async def test_search_success(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """A plain search returns a formatted response with products."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = ChatRequest(
            content=SPANISH_CONTENT,
            conversation_id="c",
            user_id="u",
            marketplace_codes=("EBAY_US",),
        )
        response = await chat_service.process(request)

        assert response.is_success
        assert response.intent_type == IntentType.SEARCH

    async def test_classify_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
    ) -> None:
        """Intent classification failure returns an error response."""
        mock_gemini.classify_intent = AsyncMock(return_value=failure(GeminiError("nope")))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert not response.is_success
        assert "reformularla" in response.message

    async def test_unexpected_exception(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
    ) -> None:
        """An unexpected exception is caught and returns an error response."""
        mock_gemini.classify_intent = AsyncMock(side_effect=RuntimeError("boom"))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert not response.is_success
        assert "error" in response.message.lower()

    async def test_extract_search_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
    ) -> None:
        """Search-intent extraction failure returns an error response."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=failure(GeminiError("parse")))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert not response.is_success
        assert "específico" in response.message

    async def test_no_marketplaces(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """No marketplaces selected prompts the user to pick one."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=()
        )
        response = await chat_service.process(request)

        assert response.is_success
        assert "selecciona" in response.message.lower()

    async def test_search_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Search orchestrator failure returns an error response."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.SEARCH))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(
            return_value=failure(
                MarketplaceError(code=ErrorCode.NETWORK, message="net", marketplace_code="EBAY_US")
            )
        )

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert not response.is_success

    async def test_clarification(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
    ) -> None:
        """Clarification intent is handled without searching."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.CLARIFICATION))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert response.is_success
        assert response.intent_type == IntentType.CLARIFICATION

    async def test_comparison_defaults_to_search(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """An unmapped, non-clarification intent falls through to search."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.COMPARISON))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert response.is_success
        mock_gemini.extract_search_intent.assert_called_once()


# --------------------------------------------------------------------------- #
# more_results
# --------------------------------------------------------------------------- #
class TestMoreResults:
    """Cover the more-results handler."""

    async def test_without_context(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
    ) -> None:
        """Without a previous search, more-results asks what to search."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.MORE_RESULTS))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert response.is_success
        assert "búsqueda previa" in response.message.lower()

    async def test_with_context_reexecutes_search(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """With a previous search context, more-results re-runs the search."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.MORE_RESULTS))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = _refinement_request(
            content="Dame más resultados",
            search_params={"query": "laptop gaming"},
        )
        response = await chat_service.process(request)

        assert response.is_success
        mock_gemini.extract_search_intent.assert_called_once()


# --------------------------------------------------------------------------- #
# refinement
# --------------------------------------------------------------------------- #
class TestRefinement:
    """Cover every branch of the refinement handler."""

    async def test_no_context_treated_as_new_search(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Refinement without prior search context becomes a new search."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = ChatRequest(
            content=SPANISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        response = await chat_service.process(request)

        assert response.is_success
        mock_gemini.extract_search_intent.assert_called_once()

    async def test_extract_refinement_failure_falls_back_with_context(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Refinement extraction failure (with context) uses search-with-context."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=failure(GeminiError("parse"))
        )
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = _refinement_request(search_params={"query": "laptop gaming"})
        response = await chat_service.process(request)

        assert response.is_success
        # search-with-context builds a combined query and runs a normal search
        mock_gemini.extract_search_intent.assert_called_once()

    async def test_full_filter_criteria_and_sort_preference(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """All filter criteria plus a valid sort preference are applied."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(
                    refinement_type="filter",
                    original_query="filtra",
                    filter_criteria={
                        "max_price": "500",
                        "min_price": "100",
                        "condition": "used",
                        "free_shipping": "true",
                        "min_seller_rating": "4.5",
                    },
                    sort_preference="price_asc",
                )
            )
        )
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        # Rich search_params exercises _build_context reconstruction branches too:
        # a system message (unknown role), an assistant with no params, and one with
        # a mix of valid/invalid sort_criteria and present min/max prices.
        request = _refinement_request(
            extra_history=(
                {"role": "system", "content": "ignored"},
                {"role": "assistant", "content": "no params"},
            ),
            search_params={
                "query": "laptop gaming",
                "original_query": "Busco laptop gaming",
                "sort_criteria": ["price_asc", "bogus_sort"],
                "min_price": 100,
                "max_price": 1000,
                "condition": "new",
                "require_free_shipping": True,
                "min_seller_rating": 4.0,
                "limit": 20,
                "ebay_category_id": "111",
                "meli_category_id": "MLC222",
            },
        )
        response = await chat_service.process(request)

        assert response.is_success
        search_request = mock_search.search.call_args[0][0]
        assert search_request.intent.max_price == Decimal("500")
        assert search_request.intent.min_price == Decimal("100")
        assert search_request.intent.condition == "used"
        assert search_request.intent.require_free_shipping is True
        assert search_request.intent.min_seller_rating == 4.5
        assert search_request.intent.sort_criteria[0] == SortOrder.PRICE_ASC

    async def test_sort_preference_unknown_is_ignored(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """An unknown sort preference does not alter sort criteria."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(
                    refinement_type="filter",
                    original_query="ordena raro",
                    sort_preference="not_a_real_sort",
                )
            )
        )
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = _refinement_request(search_params={"query": "laptop gaming"})
        response = await chat_service.process(request)

        assert response.is_success

    async def test_refinement_type_cheapest(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """The 'cheapest' refinement forces a price-ascending sort."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(refinement_type="cheapest", original_query="el más barato")
            )
        )
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = _refinement_request(search_params={"query": "laptop gaming"})
        response = await chat_service.process(request)

        assert response.is_success
        search_request = mock_search.search.call_args[0][0]
        assert search_request.intent.sort_criteria[0] == SortOrder.PRICE_ASC

    async def test_refinement_type_best_rated_defaults_rating(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """'best_rated' with no rating defaults the seller rating to 4.0."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(refinement_type="best_rated", original_query="el mejor")
            )
        )
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = _refinement_request(search_params={"query": "laptop gaming"})
        response = await chat_service.process(request)

        assert response.is_success
        search_request = mock_search.search.call_args[0][0]
        assert search_request.intent.min_seller_rating == 4.0
        assert search_request.intent.sort_criteria[0] == SortOrder.BEST_SELLER

    async def test_refinement_type_best_rated_keeps_existing_rating(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """'best_rated' keeps an explicitly provided seller rating."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(
                    refinement_type="best_rated",
                    original_query="el mejor",
                    filter_criteria={"min_seller_rating": "4.8"},
                )
            )
        )
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = _refinement_request(search_params={"query": "laptop gaming"})
        response = await chat_service.process(request)

        assert response.is_success
        search_request = mock_search.search.call_args[0][0]
        assert search_request.intent.min_seller_rating == 4.8

    async def test_refinement_search_failure(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
    ) -> None:
        """A failing refinement search returns an error response."""
        mock_gemini.classify_intent = AsyncMock(return_value=success(IntentType.REFINEMENT))
        mock_gemini.extract_refinement_intent = AsyncMock(
            return_value=success(
                RefinementIntent(refinement_type="filter", original_query="filtra")
            )
        )
        mock_search.search = AsyncMock(
            return_value=failure(
                MarketplaceError(code=ErrorCode.NETWORK, message="net", marketplace_code="EBAY_US")
            )
        )

        request = _refinement_request(search_params={"query": "laptop gaming"})
        response = await chat_service.process(request)

        assert not response.is_success
        assert "filtro" in response.message.lower()


# --------------------------------------------------------------------------- #
# _handle_search_with_context direct branch
# --------------------------------------------------------------------------- #
class TestHandleSearchWithContext:
    """Cover the search-with-context handler's no-intent branch directly."""

    async def test_no_last_intent_delegates_to_search(
        self,
        chat_service: ChatService,
        mock_gemini: MagicMock,
        mock_search: MagicMock,
        sample_search_intent: SearchIntent,
    ) -> None:
        """Without a prior intent, it delegates straight to a plain search."""
        chat_service._current_user_content = ENGLISH_CONTENT
        mock_gemini.extract_search_intent = AsyncMock(return_value=success(sample_search_intent))
        mock_search.search = AsyncMock(return_value=success(_aggregated()))

        request = ChatRequest(
            content=ENGLISH_CONTENT, conversation_id="c", user_id="u", marketplace_codes=("MLC",)
        )
        context = ConversationContext(selected_marketplaces=["MLC"])

        response = await chat_service._handle_search_with_context(request, context)

        assert response.is_success
        mock_gemini.extract_search_intent.assert_called_once()


# --------------------------------------------------------------------------- #
# response formatting (direct calls for precise language/branch control)
# --------------------------------------------------------------------------- #
class TestFormatSearchResponse:
    """Cover every branch of ``_format_search_response``."""

    def test_no_results_failed_spanish(self, chat_service: ChatService) -> None:
        """No results + failed marketplaces, Spanish."""
        chat_service._current_user_content = SPANISH_CONTENT
        result = _aggregated(
            products=[], marketplace_results=[_failed_marketplace()], total_count=0
        )
        message = chat_service._format_search_response("laptop", result)
        assert "problemas" in message.lower()
        assert "MLC" in message

    def test_no_results_failed_english(self, chat_service: ChatService) -> None:
        """No results + failed marketplaces, English."""
        chat_service._current_user_content = ENGLISH_CONTENT
        result = _aggregated(
            products=[], marketplace_results=[_failed_marketplace()], total_count=0
        )
        message = chat_service._format_search_response("laptop", result)
        assert "issues" in message.lower()
        assert "MLC" in message

    def test_no_results_no_failed_spanish(self, chat_service: ChatService) -> None:
        """No results, no failures, Spanish."""
        chat_service._current_user_content = SPANISH_CONTENT
        result = _aggregated(products=[], marketplace_results=[], total_count=0)
        message = chat_service._format_search_response("laptop", result)
        assert "no encontré" in message.lower()

    def test_no_results_no_failed_english(self, chat_service: ChatService) -> None:
        """No results, no failures, English."""
        chat_service._current_user_content = ENGLISH_CONTENT
        result = _aggregated(products=[], marketplace_results=[], total_count=0)
        message = chat_service._format_search_response("laptop", result)
        assert "couldn't find results" in message.lower()

    def test_results_spanish_more_available_best_price_no_tax(
        self, chat_service: ChatService
    ) -> None:
        """Spanish, more available, best price without tax info."""
        chat_service._current_user_content = SPANISH_CONTENT
        result = _aggregated(
            products=[_enriched(is_best_price=True, tax_info=None)],
            marketplace_results=[_ok_marketplace()],
            total_count=100,
            has_more=True,
        )
        message = chat_service._format_search_response("laptop gaming", result)
        assert "encontré" in message.lower()
        assert "disponibles" in message.lower()
        assert "más resultados" in message.lower()
        assert "mejor precio" in message.lower()

    def test_results_english_more_available_best_price_tax_no_de_minimis(
        self, chat_service: ChatService
    ) -> None:
        """English, more available, plural marketplaces, taxed best price."""
        chat_service._current_user_content = ENGLISH_CONTENT
        result = _aggregated(
            products=[_enriched(is_best_price=True, tax_info=_tax(de_minimis=False))],
            marketplace_results=[_ok_marketplace("EBAY_US"), _ok_marketplace("EBAY_UK")],
            total_count=100,
            has_more=True,
        )
        message = chat_service._format_search_response("laptop gaming", result)
        assert "found" in message.lower()
        assert "available" in message.lower()
        assert "more results" in message.lower()
        assert "marketplaces" in message.lower()
        assert "taxes" in message.lower()
        assert "tax exempt" not in message.lower()

    def test_results_english_de_minimis(self, chat_service: ChatService) -> None:
        """English tax-exempt (de minimis) best price."""
        chat_service._current_user_content = ENGLISH_CONTENT
        result = _aggregated(
            products=[_enriched(is_best_price=True, tax_info=_tax(de_minimis=True))],
            marketplace_results=[_ok_marketplace()],
            total_count=100,
            has_more=True,
        )
        message = chat_service._format_search_response("laptop gaming", result)
        assert "tax exempt" in message.lower()

    def test_results_spanish_no_more_taxed_no_de_minimis(self, chat_service: ChatService) -> None:
        """Spanish, no more results, total == count, taxed best price."""
        chat_service._current_user_content = SPANISH_CONTENT
        result = _aggregated(
            products=[_enriched(is_best_price=True, tax_info=_tax(de_minimis=False))],
            marketplace_results=[_ok_marketplace()],
            total_count=1,
            has_more=False,
        )
        message = chat_service._format_search_response("laptop gaming", result)
        assert "impuestos" in message.lower()
        assert "disponibles" not in message.lower()
        assert "más resultados" not in message.lower()
        assert "exento" not in message.lower()

    def test_results_spanish_de_minimis(self, chat_service: ChatService) -> None:
        """Spanish tax-exempt (de minimis) best price."""
        chat_service._current_user_content = SPANISH_CONTENT
        result = _aggregated(
            products=[_enriched(is_best_price=True, tax_info=_tax(de_minimis=True))],
            marketplace_results=[_ok_marketplace()],
            total_count=1,
            has_more=False,
        )
        message = chat_service._format_search_response("laptop gaming", result)
        assert "exento" in message.lower()

    def test_results_english_no_more_no_best_price(self, chat_service: ChatService) -> None:
        """English, total == count, no more results, no best-price product."""
        chat_service._current_user_content = ENGLISH_CONTENT
        result = _aggregated(
            products=[_enriched(is_best_price=False, tax_info=None)],
            marketplace_results=[_ok_marketplace()],
            total_count=1,
            has_more=False,
        )
        message = chat_service._format_search_response("laptop gaming", result)
        assert "found" in message.lower()
        assert "available" not in message.lower()
        assert "more results" not in message.lower()
        assert "best price" not in message.lower()


# --------------------------------------------------------------------------- #
# _create_error_response default-English fallback + close
# --------------------------------------------------------------------------- #
class TestMisc:
    """Cover the error-response default fallback and close."""

    def test_create_error_response_defaults_english_to_spanish(
        self, chat_service: ChatService
    ) -> None:
        """When no English message is given it falls back to the Spanish text."""
        chat_service._current_user_content = ENGLISH_CONTENT
        response = chat_service._create_error_response("Solo mensaje")
        assert response.message == "Solo mensaje"
        assert not response.is_success

    async def test_close_closes_search(
        self,
        chat_service: ChatService,
        mock_search: MagicMock,
    ) -> None:
        """Close delegates to the search orchestrator."""
        mock_search.close = AsyncMock()
        await chat_service.close()
        mock_search.close.assert_called_once()
