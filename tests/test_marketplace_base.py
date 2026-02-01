"""Tests for marketplace base types and protocols."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.marketplaces.base import (
    ProductResult,
    SearchParams,
    SearchResult,
    SortOrder,
)


class TestSortOrder:
    """Tests for SortOrder enum."""

    def test_sort_order_values(self) -> None:
        """SortOrder should have expected values."""
        assert SortOrder.RELEVANCE.value == "relevance"
        assert SortOrder.PRICE_ASC.value == "price_asc"
        assert SortOrder.PRICE_DESC.value == "price_desc"
        assert SortOrder.NEWEST.value == "newest"
        assert SortOrder.BEST_SELLER.value == "best_seller"


class TestSearchParams:
    """Tests for SearchParams dataclass."""

    def test_create_with_defaults(self) -> None:
        """SearchParams can be created with just a query."""
        params = SearchParams(query="laptop")

        assert params.query == "laptop"
        assert params.sort == SortOrder.RELEVANCE
        assert params.min_price is None
        assert params.max_price is None
        assert params.limit == 20
        assert params.offset == 0

    def test_create_with_all_params(self) -> None:
        """SearchParams can be created with all parameters."""
        params = SearchParams(
            query="gaming laptop",
            sort=SortOrder.PRICE_ASC,
            min_price=Decimal("100.00"),
            max_price=Decimal("1000.00"),
            limit=50,
            offset=10,
        )

        assert params.query == "gaming laptop"
        assert params.sort == SortOrder.PRICE_ASC
        assert params.min_price == Decimal("100.00")
        assert params.max_price == Decimal("1000.00")
        assert params.limit == 50
        assert params.offset == 10

    def test_limit_validation_min(self) -> None:
        """SearchParams should reject limit < 1."""
        with pytest.raises(ValueError, match="limit must be at least 1"):
            SearchParams(query="test", limit=0)

    def test_limit_validation_max(self) -> None:
        """SearchParams should reject limit > 100."""
        with pytest.raises(ValueError, match="limit cannot exceed 100"):
            SearchParams(query="test", limit=101)

    def test_offset_validation(self) -> None:
        """SearchParams should reject negative offset."""
        with pytest.raises(ValueError, match="offset cannot be negative"):
            SearchParams(query="test", offset=-1)

    def test_min_price_validation(self) -> None:
        """SearchParams should reject negative min_price."""
        with pytest.raises(ValueError, match="min_price cannot be negative"):
            SearchParams(query="test", min_price=Decimal("-1"))

    def test_max_price_validation(self) -> None:
        """SearchParams should reject negative max_price."""
        with pytest.raises(ValueError, match="max_price cannot be negative"):
            SearchParams(query="test", max_price=Decimal("-1"))

    def test_price_range_validation(self) -> None:
        """SearchParams should reject min_price > max_price."""
        with pytest.raises(ValueError, match="min_price cannot be greater than max_price"):
            SearchParams(
                query="test",
                min_price=Decimal("100"),
                max_price=Decimal("50"),
            )


class TestProductResult:
    """Tests for ProductResult dataclass."""

    @pytest.fixture()
    def sample_product(self) -> ProductResult:
        """Create a sample product for testing."""
        return ProductResult(
            id="123",
            marketplace_code="EBAY_US",
            title="Test Laptop",
            price=Decimal("999.99"),
            currency="USD",
            url="https://example.com/product/123",
            image_url="https://example.com/image.jpg",
            seller_name="TestSeller",
            seller_rating=4.5,
            condition="new",
            shipping_cost=Decimal("10.00"),
            free_shipping=False,
            available_quantity=5,
        )

    def test_create_product_minimal(self) -> None:
        """ProductResult can be created with required fields only."""
        product = ProductResult(
            id="123",
            marketplace_code="MLC",
            title="Test Product",
            price=Decimal("100"),
            currency="CLP",
            url="https://example.com",
        )

        assert product.id == "123"
        assert product.marketplace_code == "MLC"
        assert product.title == "Test Product"
        assert product.image_url is None
        assert product.free_shipping is False

    def test_total_price_with_shipping(self, sample_product: ProductResult) -> None:
        """total_price should include shipping cost."""
        assert sample_product.total_price == Decimal("1009.99")

    def test_total_price_free_shipping(self) -> None:
        """total_price should not add shipping when free."""
        product = ProductResult(
            id="123",
            marketplace_code="EBAY_US",
            title="Test",
            price=Decimal("100"),
            currency="USD",
            url="https://example.com",
            shipping_cost=Decimal("10"),
            free_shipping=True,
        )

        assert product.total_price == Decimal("100")

    def test_total_price_no_shipping(self) -> None:
        """total_price should equal price when no shipping cost."""
        product = ProductResult(
            id="123",
            marketplace_code="EBAY_US",
            title="Test",
            price=Decimal("100"),
            currency="USD",
            url="https://example.com",
        )

        assert product.total_price == Decimal("100")


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    @pytest.fixture()
    def sample_products(self) -> tuple[ProductResult, ...]:
        """Create sample products for testing."""
        return (
            ProductResult(
                id="1",
                marketplace_code="EBAY_US",
                title="Product 1",
                price=Decimal("100"),
                currency="USD",
                url="https://example.com/1",
            ),
            ProductResult(
                id="2",
                marketplace_code="EBAY_US",
                title="Product 2",
                price=Decimal("200"),
                currency="USD",
                url="https://example.com/2",
            ),
        )

    def test_create_search_result(self, sample_products: tuple[ProductResult, ...]) -> None:
        """SearchResult can be created with products."""
        result = SearchResult(
            products=sample_products,
            total_count=100,
            has_more=True,
            marketplace_code="EBAY_US",
        )

        assert result.total_count == 100
        assert result.has_more is True
        assert result.marketplace_code == "EBAY_US"

    def test_count_property(self, sample_products: tuple[ProductResult, ...]) -> None:
        """count should return number of products in result."""
        result = SearchResult(
            products=sample_products,
            total_count=100,
            has_more=True,
            marketplace_code="EBAY_US",
        )

        assert result.count == 2

    def test_empty_result(self) -> None:
        """SearchResult can be empty."""
        result = SearchResult(
            products=(),
            total_count=0,
            has_more=False,
            marketplace_code="MLC",
        )

        assert result.count == 0
        assert result.total_count == 0
