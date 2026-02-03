"""Tests for search orchestrator."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.result import Failure, Success, failure, success
from services.gemini.types import SearchIntent
from services.marketplaces.base import ProductResult, SearchResult, SortOrder
from services.marketplaces.errors import NetworkError
from services.search.orchestrator import SearchOrchestrator, SearchOrchestratorError
from services.search.types import SearchRequest, TaxInfo
from services.taxes import TaxBreakdown, TaxCalculatorService


class TestSearchOrchestratorError:
    """Tests for SearchOrchestratorError."""

    def test_create_with_message(self) -> None:
        """Error can be created with message."""
        error = SearchOrchestratorError("Test error")

        assert error.message == "Test error"
        assert error.details is None
        assert str(error) == "Test error"

    def test_create_with_details(self) -> None:
        """Error can be created with details."""
        error = SearchOrchestratorError("Test error", details="More info")

        assert error.details == "More info"


class TestSearchOrchestratorInit:
    """Tests for SearchOrchestrator initialization."""

    def test_init(self) -> None:
        """Orchestrator can be initialized."""
        factory = MagicMock()
        orchestrator = SearchOrchestrator(factory)

        assert orchestrator._factory == factory
        assert orchestrator._default_timeout == 30.0
        assert orchestrator._adapters == {}

    def test_init_with_custom_timeout(self) -> None:
        """Orchestrator can have custom timeout."""
        factory = MagicMock()
        orchestrator = SearchOrchestrator(factory, default_timeout=60.0)

        assert orchestrator._default_timeout == 60.0


class TestSearchOrchestratorSearch:
    """Tests for search method."""

    @pytest.fixture()
    def mock_factory(self) -> MagicMock:
        """Create a mock factory."""
        return MagicMock()

    @pytest.fixture()
    def mock_adapter(self) -> AsyncMock:
        """Create a mock adapter."""
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        return adapter

    @pytest.fixture()
    def sample_product(self) -> ProductResult:
        """Create a sample product."""
        return ProductResult(
            id="123",
            marketplace_code="MLC",
            title="Laptop Gaming",
            price=Decimal("999.99"),
            currency="CLP",
            url="https://example.com/123",
        )

    @pytest.fixture()
    def sample_intent(self) -> SearchIntent:
        """Create a sample search intent."""
        return SearchIntent(
            query="laptop gaming",
            original_query="buscar laptop gaming",
            sort_criteria=(SortOrder.PRICE_ASC,),
            limit=20,
        )

    @pytest.mark.asyncio
    async def test_search_no_marketplaces(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """Search should fail with no marketplaces."""
        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=(),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Failure)
        assert "No marketplaces specified" in result.error.message

    @pytest.mark.asyncio
    async def test_search_invalid_marketplaces(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """Search should fail when all marketplaces are invalid."""
        mock_factory.get_adapter.return_value = Failure(MagicMock())
        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("INVALID",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Failure)
        assert "No valid marketplaces" in result.error.message

    @pytest.mark.asyncio
    async def test_search_success_single_marketplace(
        self,
        mock_factory: MagicMock,
        mock_adapter: AsyncMock,
        sample_product: ProductResult,
        sample_intent: SearchIntent,
    ) -> None:
        """Search should succeed with single marketplace."""
        mock_factory.get_adapter.return_value = Success(mock_adapter)
        mock_adapter.search.return_value = success(
            SearchResult(
                products=(sample_product,),
                total_count=1,
                has_more=False,
                marketplace_code="MLC",
            )
        )

        orchestrator = SearchOrchestrator(mock_factory)
        request = SearchRequest(
            intent=sample_intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert result.value.total_count == 1
        assert len(result.value.products) == 1
        assert result.value.products[0].marketplace_code == "MLC"
        assert result.value.successful_marketplaces == 1

    @pytest.mark.asyncio
    async def test_search_success_multiple_marketplaces(
        self,
        mock_factory: MagicMock,
        sample_intent: SearchIntent,
    ) -> None:
        """Search should aggregate results from multiple marketplaces."""
        # Create two mock adapters
        adapter1 = AsyncMock()
        adapter1.marketplace_code = "MLC"
        adapter1.marketplace_name = "MercadoLibre Chile"
        adapter1.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="MLC",
                        title="Laptop 1",
                        price=Decimal("100"),
                        currency="CLP",
                        url="https://mlc.com/1",
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="MLC",
            )
        )

        adapter2 = AsyncMock()
        adapter2.marketplace_code = "EBAY_US"
        adapter2.marketplace_name = "eBay United States"
        adapter2.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="2",
                        marketplace_code="EBAY_US",
                        title="Laptop 2",
                        price=Decimal("200"),
                        currency="USD",
                        url="https://ebay.com/2",
                    ),
                ),
                total_count=1,
                has_more=True,
                marketplace_code="EBAY_US",
            )
        )

        def get_adapter_side_effect(code: str) -> Any:
            if code == "MLC":
                return Success(adapter1)
            elif code == "EBAY_US":
                return Success(adapter2)
            return Failure(MagicMock())

        mock_factory.get_adapter.side_effect = get_adapter_side_effect

        orchestrator = SearchOrchestrator(mock_factory)
        request = SearchRequest(
            intent=sample_intent,
            marketplace_codes=("MLC", "EBAY_US"),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert result.value.total_count == 2
        # With PRICE_ASC, cheaper should be first
        assert result.value.products[0].product.price == Decimal("100")
        assert result.value.products[0].is_best_price is True
        assert result.value.has_more is True

    @pytest.mark.asyncio
    async def test_search_partial_failure(
        self,
        mock_factory: MagicMock,
        sample_intent: SearchIntent,
    ) -> None:
        """Search should handle partial marketplace failures."""
        adapter1 = AsyncMock()
        adapter1.marketplace_code = "MLC"
        adapter1.marketplace_name = "MercadoLibre Chile"
        adapter1.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="MLC",
                        title="Laptop",
                        price=Decimal("100"),
                        currency="CLP",
                        url="https://mlc.com/1",
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="MLC",
            )
        )

        adapter2 = AsyncMock()
        adapter2.marketplace_code = "EBAY_US"
        adapter2.marketplace_name = "eBay United States"
        adapter2.search.return_value = failure(NetworkError("Connection refused"))

        def get_adapter_side_effect(code: str) -> Any:
            if code == "MLC":
                return Success(adapter1)
            elif code == "EBAY_US":
                return Success(adapter2)
            return Failure(MagicMock())

        mock_factory.get_adapter.side_effect = get_adapter_side_effect

        orchestrator = SearchOrchestrator(mock_factory)
        request = SearchRequest(
            intent=sample_intent,
            marketplace_codes=("MLC", "EBAY_US"),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert result.value.successful_marketplaces == 1
        assert "EBAY_US" in result.value.failed_marketplaces

    @pytest.mark.asyncio
    async def test_search_uses_cached_adapter(
        self,
        mock_factory: MagicMock,
        mock_adapter: AsyncMock,
        sample_product: ProductResult,
        sample_intent: SearchIntent,
    ) -> None:
        """Search should reuse cached adapters."""
        mock_factory.get_adapter.return_value = Success(mock_adapter)
        mock_adapter.search.return_value = success(
            SearchResult(
                products=(sample_product,),
                total_count=1,
                has_more=False,
                marketplace_code="MLC",
            )
        )

        orchestrator = SearchOrchestrator(mock_factory)
        request = SearchRequest(
            intent=sample_intent,
            marketplace_codes=("MLC",),
        )

        # First search
        await orchestrator.search(request)
        # Second search
        await orchestrator.search(request)

        # Factory should only be called once (adapter cached)
        assert mock_factory.get_adapter.call_count == 1


class TestSearchOrchestratorSorting:
    """Tests for sorting functionality."""

    @pytest.fixture()
    def mock_factory(self) -> MagicMock:
        """Create a mock factory."""
        return MagicMock()

    @pytest.fixture()
    def products(self) -> list[ProductResult]:
        """Create sample products."""
        return [
            ProductResult(
                id="1",
                marketplace_code="MLC",
                title="Cheap",
                price=Decimal("100"),
                currency="CLP",
                url="https://example.com/1",
                seller_rating=3.0,
            ),
            ProductResult(
                id="2",
                marketplace_code="MLC",
                title="Expensive",
                price=Decimal("500"),
                currency="CLP",
                url="https://example.com/2",
                seller_rating=5.0,
            ),
            ProductResult(
                id="3",
                marketplace_code="MLC",
                title="Medium",
                price=Decimal("250"),
                currency="CLP",
                url="https://example.com/3",
                seller_rating=4.0,
            ),
        ]

    @pytest.mark.asyncio
    async def test_sort_price_asc(
        self,
        mock_factory: MagicMock,
        products: list[ProductResult],
    ) -> None:
        """Products should be sorted by price ascending."""
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=tuple(products),
                total_count=3,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.PRICE_ASC,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        prices = [p.product.price for p in result.value.products]
        assert prices == [Decimal("100"), Decimal("250"), Decimal("500")]

    @pytest.mark.asyncio
    async def test_sort_price_desc(
        self,
        mock_factory: MagicMock,
        products: list[ProductResult],
    ) -> None:
        """Products should be sorted by price descending."""
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=tuple(products),
                total_count=3,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.PRICE_DESC,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        prices = [p.product.price for p in result.value.products]
        assert prices == [Decimal("500"), Decimal("250"), Decimal("100")]

    @pytest.mark.asyncio
    async def test_sort_best_seller(
        self,
        mock_factory: MagicMock,
        products: list[ProductResult],
    ) -> None:
        """Products should be sorted by seller rating."""
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=tuple(products),
                total_count=3,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.BEST_SELLER,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        ratings = [p.product.seller_rating for p in result.value.products]
        assert ratings == [5.0, 4.0, 3.0]

    @pytest.mark.asyncio
    async def test_sort_newest(
        self,
        mock_factory: MagicMock,
        products: list[ProductResult],
    ) -> None:
        """Newest sort should maintain order (API handles sorting)."""
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=tuple(products),
                total_count=3,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.NEWEST,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        # Order should be maintained
        assert len(result.value.products) == 3


class TestSearchOrchestratorInterleaving:
    """Tests for result interleaving."""

    @pytest.mark.asyncio
    async def test_interleave_results(self) -> None:
        """Results should be interleaved for relevance sort."""
        mock_factory = MagicMock()

        adapter1 = AsyncMock()
        adapter1.marketplace_code = "MLC"
        adapter1.marketplace_name = "MercadoLibre Chile"
        adapter1.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="mlc1",
                        marketplace_code="MLC",
                        title="MLC 1",
                        price=Decimal("100"),
                        currency="CLP",
                        url="https://mlc.com/1",
                    ),
                    ProductResult(
                        id="mlc2",
                        marketplace_code="MLC",
                        title="MLC 2",
                        price=Decimal("200"),
                        currency="CLP",
                        url="https://mlc.com/2",
                    ),
                ),
                total_count=2,
                has_more=False,
                marketplace_code="MLC",
            )
        )

        adapter2 = AsyncMock()
        adapter2.marketplace_code = "EBAY_US"
        adapter2.marketplace_name = "eBay United States"
        adapter2.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="ebay1",
                        marketplace_code="EBAY_US",
                        title="eBay 1",
                        price=Decimal("150"),
                        currency="USD",
                        url="https://ebay.com/1",
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="EBAY_US",
            )
        )

        def get_adapter_side_effect(code: str) -> Any:
            if code == "MLC":
                return Success(adapter1)
            elif code == "EBAY_US":
                return Success(adapter2)
            return Failure(MagicMock())

        mock_factory.get_adapter.side_effect = get_adapter_side_effect

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.RELEVANCE,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC", "EBAY_US"),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        # Results should be interleaved: MLC, EBAY, MLC
        codes = [p.marketplace_code for p in result.value.products]
        assert len(codes) == 3


class TestSearchOrchestratorPriceMarking:
    """Tests for best price marking."""

    @pytest.mark.asyncio
    async def test_mark_best_price(self) -> None:
        """Cheapest product should be marked as best price."""
        mock_factory = MagicMock()

        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="MLC",
                        title="Expensive",
                        price=Decimal("500"),
                        currency="CLP",
                        url="https://mlc.com/1",
                    ),
                    ProductResult(
                        id="2",
                        marketplace_code="MLC",
                        title="Cheap",
                        price=Decimal("100"),
                        currency="CLP",
                        url="https://mlc.com/2",
                    ),
                ),
                total_count=2,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.RELEVANCE,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        # Find the best price product
        best_price_products = [p for p in result.value.products if p.is_best_price]
        assert len(best_price_products) == 1
        assert best_price_products[0].product.price == Decimal("100")
        assert best_price_products[0].price_rank == 1


class TestSearchOrchestratorTimeout:
    """Tests for timeout handling."""

    @pytest.mark.asyncio
    async def test_search_timeout(self) -> None:
        """Search should handle timeouts gracefully."""
        import asyncio

        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"

        async def slow_search(*args: Any, **kwargs: Any) -> Any:
            await asyncio.sleep(10)  # Will timeout
            return success(
                SearchResult(products=(), total_count=0, has_more=False, marketplace_code="MLC")
            )

        adapter.search = slow_search
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory, default_timeout=0.1)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert result.value.successful_marketplaces == 0
        assert "MLC" in result.value.failed_marketplaces


class TestSearchOrchestratorClose:
    """Tests for close method."""

    @pytest.mark.asyncio
    async def test_close_adapters(self) -> None:
        """Close should close all cached adapters."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        await orchestrator.search(request)
        await orchestrator.close()

        adapter.close.assert_called_once()
        assert orchestrator._adapters == {}

    @pytest.mark.asyncio
    async def test_close_handles_errors(self) -> None:
        """Close should handle adapter close errors."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        adapter.close.side_effect = Exception("Close error")
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        await orchestrator.search(request)
        # Should not raise
        await orchestrator.close()


class TestSearchOrchestratorHealthcheck:
    """Tests for healthcheck method."""

    @pytest.mark.asyncio
    async def test_healthcheck_all_healthy(self) -> None:
        """Healthcheck should return status for all adapters."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        adapter.healthcheck.return_value = True
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        await orchestrator.search(request)
        result = await orchestrator.healthcheck()

        assert result == {"MLC": True}

    @pytest.mark.asyncio
    async def test_healthcheck_handles_errors(self) -> None:
        """Healthcheck should handle adapter errors."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        adapter.healthcheck.side_effect = Exception("Health error")
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        await orchestrator.search(request)
        result = await orchestrator.healthcheck()

        assert result == {"MLC": False}


class TestSearchOrchestratorEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_search_exception_in_marketplace(self) -> None:
        """Search should handle unexpected exceptions."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.side_effect = RuntimeError("Unexpected error")
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert "MLC" in result.value.failed_marketplaces

    @pytest.mark.asyncio
    async def test_search_all_multiple_marketplaces(self) -> None:
        """_search_all should continue after processing an exception."""
        mock_factory = MagicMock()

        # First adapter raises exception
        adapter1 = AsyncMock()
        adapter1.marketplace_code = "EBAY_US"
        adapter1.marketplace_name = "eBay United States"

        # We need to make the exception escape _search_marketplace's try/except
        # by patching it to raise directly
        adapter1.search.side_effect = RuntimeError("Escaped exception")

        # Second adapter returns valid result
        adapter2 = AsyncMock()
        adapter2.marketplace_code = "MLC"
        adapter2.marketplace_name = "MercadoLibre Chile"
        adapter2.search.return_value = success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code="MLC",
            )
        )

        def get_adapter_side_effect(code: str) -> Any:
            if code == "EBAY_US":
                return Success(adapter1)
            elif code == "MLC":
                return Success(adapter2)
            return Failure(MagicMock())

        mock_factory.get_adapter.side_effect = get_adapter_side_effect

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("EBAY_US", "MLC"),
        )

        result = await orchestrator.search(request)

        # One should succeed, one should fail
        assert isinstance(result, Success)
        assert result.value.successful_marketplaces == 1
        assert "EBAY_US" in result.value.failed_marketplaces

    @pytest.mark.asyncio
    async def test_sort_empty_products(self) -> None:
        """Sorting should handle empty product list."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(SortOrder.PRICE_ASC,),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert result.value.products == []

    @pytest.mark.asyncio
    async def test_mark_best_price_empty(self) -> None:
        """Best price marking should handle empty list."""
        mock_factory = MagicMock()
        orchestrator = SearchOrchestrator(mock_factory)

        # Directly test private method
        orchestrator._mark_best_prices([])  # Should not raise

    @pytest.mark.asyncio
    async def test_interleave_empty(self) -> None:
        """Interleaving should handle empty list."""
        mock_factory = MagicMock()
        orchestrator = SearchOrchestrator(mock_factory)

        result = orchestrator._interleave_results([])
        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_none_sort_order(self) -> None:
        """Search should handle None sort order."""
        mock_factory = MagicMock()
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="MLC",
                        title="Laptop",
                        price=Decimal("100"),
                        currency="CLP",
                        url="https://mlc.com/1",
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory)
        intent = SearchIntent(
            query="laptop",
            original_query="laptop",
            sort_criteria=(),
        )
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert len(result.value.products) == 1


class TestSearchOrchestratorTaxCalculation:
    """Tests for tax calculation integration."""

    @pytest.fixture()
    def mock_factory(self) -> MagicMock:
        """Create a mock factory."""
        return MagicMock()

    @pytest.fixture()
    def mock_tax_calculator(self) -> MagicMock:
        """Create a mock tax calculator."""
        return MagicMock(spec=TaxCalculatorService)

    @pytest.mark.asyncio
    async def test_search_with_destination_country(
        self,
        mock_factory: MagicMock,
        mock_tax_calculator: MagicMock,
    ) -> None:
        """Search should calculate taxes when destination country specified."""
        adapter = AsyncMock()
        adapter.marketplace_code = "EBAY_US"
        adapter.marketplace_name = "eBay United States"
        adapter.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="EBAY_US",
                        title="Laptop",
                        price=Decimal("100"),
                        currency="USD",
                        url="https://ebay.com/1",
                        shipping_cost=Decimal("20"),
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="EBAY_US",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        # Mock tax calculation
        mock_tax_calculator.calculate.return_value = success(
            TaxBreakdown(
                product_price_usd=Decimal("100"),
                shipping_cost_usd=Decimal("20"),
                customs_duty=Decimal("6"),
                vat=Decimal("23.94"),
                total_taxes=Decimal("29.94"),
                total_cost=Decimal("149.94"),
                destination_country="CL",
                destination_country_name="Chile",
                vat_rate=Decimal("19"),
                customs_duty_rate=Decimal("6"),
                de_minimis_applied=False,
            )
        )

        orchestrator = SearchOrchestrator(mock_factory, tax_calculator=mock_tax_calculator)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("EBAY_US",),
            destination_country="CL",
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert len(result.value.products) == 1
        product = result.value.products[0]
        assert product.tax_info is not None
        assert product.tax_info.customs_duty == Decimal("6")
        assert product.tax_info.vat == Decimal("23.94")
        assert product.tax_info.total_with_taxes == Decimal("149.94")

    @pytest.mark.asyncio
    async def test_search_without_destination_country(
        self,
        mock_factory: MagicMock,
        mock_tax_calculator: MagicMock,
    ) -> None:
        """Search should not calculate taxes without destination country."""
        adapter = AsyncMock()
        adapter.marketplace_code = "MLC"
        adapter.marketplace_name = "MercadoLibre Chile"
        adapter.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="MLC",
                        title="Laptop",
                        price=Decimal("100"),
                        currency="CLP",
                        url="https://mlc.com/1",
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="MLC",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        orchestrator = SearchOrchestrator(mock_factory, tax_calculator=mock_tax_calculator)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
            # No destination_country
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        assert result.value.products[0].tax_info is None
        mock_tax_calculator.calculate.assert_not_called()

    @pytest.mark.asyncio
    async def test_tax_calculation_failure_handled(
        self,
        mock_factory: MagicMock,
        mock_tax_calculator: MagicMock,
    ) -> None:
        """Tax calculation failure should not break search."""
        adapter = AsyncMock()
        adapter.marketplace_code = "EBAY_US"
        adapter.marketplace_name = "eBay United States"
        adapter.search.return_value = success(
            SearchResult(
                products=(
                    ProductResult(
                        id="1",
                        marketplace_code="EBAY_US",
                        title="Laptop",
                        price=Decimal("100"),
                        currency="USD",
                        url="https://ebay.com/1",
                    ),
                ),
                total_count=1,
                has_more=False,
                marketplace_code="EBAY_US",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        # Mock tax calculation failure
        from services.taxes.service import TaxCalculatorError

        mock_tax_calculator.calculate.return_value = failure(
            TaxCalculatorError("Tax calculation failed")
        )

        orchestrator = SearchOrchestrator(mock_factory, tax_calculator=mock_tax_calculator)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("EBAY_US",),
            destination_country="CL",
        )

        result = await orchestrator.search(request)

        # Search should succeed, just without tax info
        assert isinstance(result, Success)
        assert result.value.products[0].tax_info is None

    @pytest.mark.asyncio
    async def test_best_price_considers_taxes(
        self,
        mock_factory: MagicMock,
        mock_tax_calculator: MagicMock,
    ) -> None:
        """Best price should consider total with taxes."""
        adapter = AsyncMock()
        adapter.marketplace_code = "EBAY_US"
        adapter.marketplace_name = "eBay United States"
        adapter.search.return_value = success(
            SearchResult(
                products=(
                    # Cheaper base price but higher taxes
                    ProductResult(
                        id="1",
                        marketplace_code="EBAY_US",
                        title="Laptop 1",
                        price=Decimal("100"),
                        currency="USD",
                        url="https://ebay.com/1",
                    ),
                    # Higher base price but lower taxes
                    ProductResult(
                        id="2",
                        marketplace_code="EBAY_US",
                        title="Laptop 2",
                        price=Decimal("150"),
                        currency="USD",
                        url="https://ebay.com/2",
                    ),
                ),
                total_count=2,
                has_more=False,
                marketplace_code="EBAY_US",
            )
        )
        mock_factory.get_adapter.return_value = Success(adapter)

        def calculate_taxes(request: Any) -> Any:
            if request.product_price == Decimal("100"):
                # Higher total due to shipping
                return success(
                    TaxBreakdown(
                        product_price_usd=Decimal("100"),
                        shipping_cost_usd=Decimal("0"),
                        customs_duty=Decimal("50"),
                        vat=Decimal("50"),
                        total_taxes=Decimal("100"),
                        total_cost=Decimal("200"),  # 100 + 100 taxes
                        destination_country="CL",
                        destination_country_name="Chile",
                        vat_rate=Decimal("19"),
                        customs_duty_rate=Decimal("6"),
                    )
                )
            else:
                # Lower total despite higher base price
                return success(
                    TaxBreakdown(
                        product_price_usd=Decimal("150"),
                        shipping_cost_usd=Decimal("0"),
                        customs_duty=Decimal("10"),
                        vat=Decimal("20"),
                        total_taxes=Decimal("30"),
                        total_cost=Decimal("180"),  # 150 + 30 taxes
                        destination_country="CL",
                        destination_country_name="Chile",
                        vat_rate=Decimal("19"),
                        customs_duty_rate=Decimal("6"),
                    )
                )

        mock_tax_calculator.calculate.side_effect = calculate_taxes

        orchestrator = SearchOrchestrator(mock_factory, tax_calculator=mock_tax_calculator)
        intent = SearchIntent(query="laptop", original_query="laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("EBAY_US",),
            destination_country="CL",
        )

        result = await orchestrator.search(request)

        assert isinstance(result, Success)
        # Product with $150 base but $180 total should be best price
        best_price = next(p for p in result.value.products if p.is_best_price)
        assert best_price.product.price == Decimal("150")
        assert best_price.tax_info is not None
        assert best_price.tax_info.total_with_taxes == Decimal("180")

    def test_get_comparable_price_with_tax_info(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """_get_comparable_price should return total with taxes if available."""
        from services.search.types import EnrichedProduct

        orchestrator = SearchOrchestrator(mock_factory)

        product = EnrichedProduct(
            product=ProductResult(
                id="1",
                marketplace_code="EBAY_US",
                title="Laptop",
                price=Decimal("100"),
                currency="USD",
                url="https://ebay.com/1",
            ),
            marketplace_code="EBAY_US",
            marketplace_name="eBay United States",
            tax_info=TaxInfo(
                product_price_usd=Decimal("100"),
                shipping_cost_usd=Decimal("0"),
                customs_duty=Decimal("6"),
                vat=Decimal("19"),
                total_taxes=Decimal("25"),
                total_with_taxes=Decimal("125"),
                destination_country="CL",
                destination_country_name="Chile",
            ),
        )

        price = orchestrator._get_comparable_price(product)
        assert price == Decimal("125")

    def test_get_comparable_price_without_tax_info(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """_get_comparable_price should return product total without taxes."""
        from services.search.types import EnrichedProduct

        orchestrator = SearchOrchestrator(mock_factory)

        product = EnrichedProduct(
            product=ProductResult(
                id="1",
                marketplace_code="MLC",
                title="Laptop",
                price=Decimal("100"),
                currency="CLP",
                url="https://mlc.com/1",
                shipping_cost=Decimal("10"),
            ),
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
        )

        price = orchestrator._get_comparable_price(product)
        assert price == Decimal("110")  # price + shipping

    def test_init_creates_default_tax_calculator(
        self,
        mock_factory: MagicMock,
    ) -> None:
        """Orchestrator should create default tax calculator if not provided."""
        orchestrator = SearchOrchestrator(mock_factory)
        assert orchestrator._tax_calculator is not None
        assert isinstance(orchestrator._tax_calculator, TaxCalculatorService)
