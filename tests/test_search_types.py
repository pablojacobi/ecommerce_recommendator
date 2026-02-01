"""Tests for search orchestration types."""

from __future__ import annotations

from decimal import Decimal

from services.gemini.types import SearchIntent
from services.marketplaces.base import ProductResult, SortOrder
from services.search.types import (
    AggregatedResult,
    EnrichedProduct,
    MarketplaceSearchResult,
    SearchRequest,
)


class TestSearchRequest:
    """Tests for SearchRequest dataclass."""

    def test_create_with_required_fields(self) -> None:
        """SearchRequest can be created with required fields."""
        intent = SearchIntent(query="laptop", original_query="find laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC", "EBAY_US"),
        )

        assert request.intent == intent
        assert request.marketplace_codes == ("MLC", "EBAY_US")
        assert request.user_id is None

    def test_create_with_user_id(self) -> None:
        """SearchRequest can include user_id."""
        intent = SearchIntent(query="laptop", original_query="find laptop")
        request = SearchRequest(
            intent=intent,
            marketplace_codes=("MLC",),
            user_id="user123",
        )

        assert request.user_id == "user123"


class TestEnrichedProduct:
    """Tests for EnrichedProduct dataclass."""

    def test_create_with_defaults(self) -> None:
        """EnrichedProduct can be created with defaults."""
        product = ProductResult(
            id="123",
            marketplace_code="MLC",
            title="Laptop",
            price=Decimal("999.99"),
            currency="CLP",
            url="https://example.com/123",
        )
        enriched = EnrichedProduct(
            product=product,
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
        )

        assert enriched.product == product
        assert enriched.marketplace_code == "MLC"
        assert enriched.marketplace_name == "MercadoLibre Chile"
        assert enriched.is_best_price is False
        assert enriched.price_rank == 0

    def test_is_mutable(self) -> None:
        """EnrichedProduct should be mutable for price marking."""
        product = ProductResult(
            id="123",
            marketplace_code="MLC",
            title="Laptop",
            price=Decimal("999.99"),
            currency="CLP",
            url="https://example.com/123",
        )
        enriched = EnrichedProduct(
            product=product,
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
        )

        enriched.is_best_price = True
        enriched.price_rank = 1

        assert enriched.is_best_price is True
        assert enriched.price_rank == 1


class TestMarketplaceSearchResult:
    """Tests for MarketplaceSearchResult dataclass."""

    def test_create_success_result(self) -> None:
        """MarketplaceSearchResult for successful search."""
        product = ProductResult(
            id="123",
            marketplace_code="MLC",
            title="Laptop",
            price=Decimal("999.99"),
            currency="CLP",
            url="https://example.com/123",
        )
        enriched = EnrichedProduct(
            product=product,
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
        )
        result = MarketplaceSearchResult(
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
            products=[enriched],
            total_count=100,
            has_more=True,
        )

        assert result.is_success is True
        assert result.error is None
        assert len(result.products) == 1
        assert result.total_count == 100
        assert result.has_more is True

    def test_create_error_result(self) -> None:
        """MarketplaceSearchResult for failed search."""
        result = MarketplaceSearchResult(
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
            error="Connection timeout",
        )

        assert result.is_success is False
        assert result.error == "Connection timeout"
        assert result.products == []
        assert result.total_count == 0


class TestAggregatedResult:
    """Tests for AggregatedResult dataclass."""

    def test_create_with_defaults(self) -> None:
        """AggregatedResult can be created with defaults."""
        result = AggregatedResult()

        assert result.products == []
        assert result.marketplace_results == []
        assert result.total_count == 0
        assert result.sort_order is None
        assert result.query == ""
        assert result.has_more is False

    def test_successful_marketplaces_count(self) -> None:
        """successful_marketplaces should count successes."""
        success1 = MarketplaceSearchResult(
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
            total_count=10,
        )
        success2 = MarketplaceSearchResult(
            marketplace_code="EBAY_US",
            marketplace_name="eBay United States",
            total_count=20,
        )
        failed = MarketplaceSearchResult(
            marketplace_code="MLA",
            marketplace_name="MercadoLibre Argentina",
            error="Timeout",
        )

        result = AggregatedResult(
            marketplace_results=[success1, success2, failed],
        )

        assert result.successful_marketplaces == 2

    def test_failed_marketplaces_list(self) -> None:
        """failed_marketplaces should list failed codes."""
        success = MarketplaceSearchResult(
            marketplace_code="MLC",
            marketplace_name="MercadoLibre Chile",
            total_count=10,
        )
        failed1 = MarketplaceSearchResult(
            marketplace_code="MLA",
            marketplace_name="MercadoLibre Argentina",
            error="Timeout",
        )
        failed2 = MarketplaceSearchResult(
            marketplace_code="EBAY_US",
            marketplace_name="eBay United States",
            error="Rate limit",
        )

        result = AggregatedResult(
            marketplace_results=[success, failed1, failed2],
        )

        assert result.failed_marketplaces == ["MLA", "EBAY_US"]

    def test_with_sort_order(self) -> None:
        """AggregatedResult can have sort order."""
        result = AggregatedResult(
            sort_order=SortOrder.PRICE_ASC,
            query="laptop",
        )

        assert result.sort_order == SortOrder.PRICE_ASC
        assert result.query == "laptop"
