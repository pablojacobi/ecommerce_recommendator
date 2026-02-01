"""Tests for eBay marketplace adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest

from core.result import Failure, Success
from services.marketplaces.base import (
    MarketplaceAdapter,
    ProductResult,
    SearchParams,
    SearchResult,
    SortOrder,
)
from services.marketplaces.ebay.adapter import EbayAdapter
from services.marketplaces.ebay.client import EbayClient
from services.marketplaces.errors import ErrorCode, NetworkError


class TestEbayAdapterInit:
    """Tests for EbayAdapter initialization."""

    def test_adapter_implements_protocol(self) -> None:
        """Adapter should implement MarketplaceAdapter protocol."""
        mock_client = AsyncMock(spec=EbayClient)
        adapter = EbayAdapter(app_id="test", cert_id="test", client=mock_client)

        assert isinstance(adapter, MarketplaceAdapter)

    def test_marketplace_code(self) -> None:
        """marketplace_code should return marketplace ID."""
        mock_client = AsyncMock(spec=EbayClient)
        adapter = EbayAdapter(app_id="test", cert_id="test", client=mock_client)

        assert adapter.marketplace_code == "EBAY_US"

    def test_marketplace_name(self) -> None:
        """marketplace_name should return formatted name."""
        mock_client = AsyncMock(spec=EbayClient)
        adapter = EbayAdapter(app_id="test", cert_id="test", client=mock_client)

        assert adapter.marketplace_name == "eBay United States"

    def test_marketplace_name_unknown(self) -> None:
        """marketplace_name should handle unknown marketplace."""
        mock_client = AsyncMock(spec=EbayClient)
        adapter = EbayAdapter.__new__(EbayAdapter)
        adapter._marketplace_id = "UNKNOWN"
        adapter._client = mock_client

        assert adapter.marketplace_name == "eBay Unknown"


class TestEbayAdapterSearch:
    """Tests for EbayAdapter search method."""

    @pytest.fixture()
    def mock_client(self) -> AsyncMock:
        """Create a mock client."""
        return AsyncMock(spec=EbayClient)

    @pytest.fixture()
    def adapter(self, mock_client: AsyncMock) -> EbayAdapter:
        """Create adapter with mock client."""
        return EbayAdapter(app_id="test", cert_id="test", client=mock_client)

    @pytest.fixture()
    def sample_api_response(self) -> dict[str, Any]:
        """Create sample API response."""
        return {
            "itemSummaries": [
                {
                    "itemId": "v1|123456|0",
                    "title": "Gaming Laptop Intel i7",
                    "price": {"value": "599.99", "currency": "USD"},
                    "itemWebUrl": "https://www.ebay.com/itm/123456",
                    "image": {"imageUrl": "https://i.ebayimg.com/123.jpg"},
                    "condition": "New",
                    "shippingOptions": [{"shippingCost": {"value": "0.00", "currency": "USD"}}],
                    "seller": {
                        "username": "tech_store",
                        "feedbackPercentage": "99.5",
                    },
                },
                {
                    "itemId": "v1|789012|0",
                    "title": "Basic Laptop",
                    "price": {"value": "299.99", "currency": "USD"},
                    "itemWebUrl": "https://www.ebay.com/itm/789012",
                    "condition": "Used",
                    "seller": {"username": "seller2"},
                },
            ],
            "total": 100,
            "offset": 0,
            "limit": 20,
        }

    @pytest.mark.asyncio
    async def test_search_success(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
        sample_api_response: dict[str, Any],
    ) -> None:
        """search should return SearchResult on success."""
        mock_client.search.return_value = Success(sample_api_response)
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        assert isinstance(result.value, SearchResult)
        assert result.value.total_count == 100
        assert result.value.has_more is True
        assert len(result.value.products) == 2

    @pytest.mark.asyncio
    async def test_search_parses_products_correctly(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
        sample_api_response: dict[str, Any],
    ) -> None:
        """search should parse products with correct fields."""
        mock_client.search.return_value = Success(sample_api_response)
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        product = result.value.products[0]
        assert product.id == "v1|123456|0"
        assert product.title == "Gaming Laptop Intel i7"
        assert product.price == Decimal("599.99")
        assert product.currency == "USD"
        assert product.free_shipping is True
        assert product.condition == "new"
        assert product.seller_name == "tech_store"
        assert product.seller_rating is not None
        assert 4.9 < product.seller_rating <= 5.0  # 99.5%

    @pytest.mark.asyncio
    async def test_search_with_sort_order(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should pass sort order to client."""
        mock_client.search.return_value = Success(
            {"itemSummaries": [], "total": 0, "offset": 0, "limit": 20}
        )
        params = SearchParams(query="laptop", sort=SortOrder.PRICE_ASC)

        await adapter.search(params)

        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["sort"] == "price"

    @pytest.mark.asyncio
    async def test_search_with_price_filters(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should pass price filters to client."""
        mock_client.search.return_value = Success(
            {"itemSummaries": [], "total": 0, "offset": 0, "limit": 20}
        )
        params = SearchParams(
            query="laptop",
            min_price=Decimal("100"),
            max_price=Decimal("500"),
        )

        await adapter.search(params)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["min_price"] == 100.0
        assert call_kwargs["max_price"] == 500.0

    @pytest.mark.asyncio
    async def test_search_client_failure(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should propagate client errors."""
        error = NetworkError("EBAY_US", message="Connection failed")
        mock_client.search.return_value = Failure(error)
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_search_parse_exception(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should return Failure when response causes exception."""
        mock_client.search.return_value = Success(
            {"itemSummaries": None}  # Will cause AttributeError
        )
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.PARSE

    @pytest.mark.asyncio
    async def test_search_has_more_false(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should set has_more=False when no more results."""
        mock_client.search.return_value = Success(
            {
                "itemSummaries": [
                    {
                        "itemId": "123",
                        "title": "Test",
                        "price": {"value": "100", "currency": "USD"},
                        "itemWebUrl": "https://example.com",
                    }
                ],
                "total": 1,
                "offset": 0,
                "limit": 20,
            }
        )
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        assert result.value.has_more is False

    @pytest.mark.asyncio
    async def test_search_skips_unparseable_products(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should skip products that can't be parsed."""
        mock_client.search.return_value = Success(
            {
                "itemSummaries": [
                    {"invalid": "product"},  # Missing required fields
                    {
                        "itemId": "123",
                        "title": "Valid Product",
                        "price": {"value": "100", "currency": "USD"},
                        "itemWebUrl": "https://example.com",
                    },
                ],
                "total": 2,
                "offset": 0,
                "limit": 20,
            }
        )
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        assert len(result.value.products) == 1
        assert result.value.products[0].id == "123"


class TestEbayAdapterGetProduct:
    """Tests for EbayAdapter get_product method."""

    @pytest.fixture()
    def mock_client(self) -> AsyncMock:
        """Create a mock client."""
        return AsyncMock(spec=EbayClient)

    @pytest.fixture()
    def adapter(self, mock_client: AsyncMock) -> EbayAdapter:
        """Create adapter with mock client."""
        return EbayAdapter(app_id="test", cert_id="test", client=mock_client)

    @pytest.fixture()
    def sample_item_response(self) -> dict[str, Any]:
        """Create sample item response."""
        return {
            "itemId": "v1|123456|0",
            "title": "Gaming Laptop",
            "price": {"value": "599.99", "currency": "USD"},
            "itemWebUrl": "https://www.ebay.com/itm/123456",
            "image": {"imageUrl": "https://i.ebayimg.com/123.jpg"},
            "condition": "New",
            "shippingOptions": [{"shippingCost": {"value": "10.00", "currency": "USD"}}],
            "seller": {
                "username": "tech_store",
                "feedbackPercentage": "100",
            },
        }

    @pytest.mark.asyncio
    async def test_get_product_success(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
        sample_item_response: dict[str, Any],
    ) -> None:
        """get_product should return ProductResult on success."""
        mock_client.get_item.return_value = Success(sample_item_response)

        result = await adapter.get_product("123456")

        assert isinstance(result, Success)
        assert isinstance(result.value, ProductResult)
        assert result.value.id == "v1|123456|0"

    @pytest.mark.asyncio
    async def test_get_product_client_failure(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """get_product should propagate client errors."""
        error = NetworkError("EBAY_US", message="Not found")
        mock_client.get_item.return_value = Failure(error)

        result = await adapter.get_product("123456")

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_get_product_parse_error(
        self,
        adapter: EbayAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """get_product should return ParseError on invalid response."""
        mock_client.get_item.return_value = Success({"invalid": "response"})

        result = await adapter.get_product("123456")

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.PARSE


class TestEbayAdapterHealthcheck:
    """Tests for EbayAdapter healthcheck method."""

    @pytest.mark.asyncio
    async def test_healthcheck_delegates_to_client(self) -> None:
        """healthcheck should delegate to client."""
        mock_client = AsyncMock(spec=EbayClient)
        mock_client.healthcheck.return_value = True
        adapter = EbayAdapter(app_id="test", cert_id="test", client=mock_client)

        result = await adapter.healthcheck()

        assert result is True
        mock_client.healthcheck.assert_called_once()


class TestEbayAdapterClose:
    """Tests for EbayAdapter close method."""

    @pytest.mark.asyncio
    async def test_close_delegates_to_client(self) -> None:
        """close should delegate to client."""
        mock_client = AsyncMock(spec=EbayClient)
        adapter = EbayAdapter(app_id="test", cert_id="test", client=mock_client)

        await adapter.close()

        mock_client.close.assert_called_once()


class TestProductParsing:
    """Tests for product parsing edge cases."""

    @pytest.fixture()
    def adapter(self) -> EbayAdapter:
        """Create adapter for testing."""
        mock_client = AsyncMock(spec=EbayClient)
        return EbayAdapter(app_id="test", cert_id="test", client=mock_client)

    def test_parse_product_with_no_seller_rating(self, adapter: EbayAdapter) -> None:
        """_parse_product should handle missing seller rating."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
            "seller": {"username": "test"},
        }

        product = adapter._parse_product(item)

        assert product.seller_rating is None

    def test_parse_product_with_no_shipping(self, adapter: EbayAdapter) -> None:
        """_parse_product should handle missing shipping."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
        }

        product = adapter._parse_product(item)

        assert product.shipping_cost is None
        assert product.free_shipping is False

    def test_parse_product_shipping_no_value(self, adapter: EbayAdapter) -> None:
        """_parse_product should handle shipping without value."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
            "shippingOptions": [{"shippingCost": {}}],  # No value key
        }

        product = adapter._parse_product(item)

        assert product.shipping_cost is None
        assert product.free_shipping is False

    def test_parse_product_condition_mapping(self, adapter: EbayAdapter) -> None:
        """_parse_product should map conditions correctly."""
        conditions = {
            "New": "new",
            "New with tags": "new",
            "Used": "used",
            "Pre-owned": "used",
            "Certified refurbished": "refurbished",
            "Unknown": "new",  # Default
        }

        for ebay_condition, expected in conditions.items():
            item = {
                "itemId": "123",
                "title": "Test",
                "price": {"value": "100", "currency": "USD"},
                "itemWebUrl": "https://example.com",
                "condition": ebay_condition,
            }

            product = adapter._parse_product(item)

            assert product.condition == expected

    def test_parse_product_no_image(self, adapter: EbayAdapter) -> None:
        """_parse_product should handle missing image."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
        }

        product = adapter._parse_product(item)

        assert product.image_url is None

    def test_parse_product_empty_image(self, adapter: EbayAdapter) -> None:
        """_parse_product should handle empty image object."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
            "image": {},
        }

        product = adapter._parse_product(item)

        assert product.image_url is None

    def test_parse_product_with_item_href(self, adapter: EbayAdapter) -> None:
        """_parse_product should extract ID from itemHref if no itemId."""
        item = {
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemHref": "https://api.ebay.com/buy/browse/v1/item/v1|123|0",
        }

        product = adapter._parse_product(item)

        assert product.id == "v1|123|0"

    def test_parse_product_with_availability(self, adapter: EbayAdapter) -> None:
        """_parse_product should extract available quantity."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
            "estimatedAvailabilities": [{"estimatedAvailableQuantity": 5}],
        }

        product = adapter._parse_product(item)

        assert product.available_quantity == 5

    def test_parse_product_no_availability(self, adapter: EbayAdapter) -> None:
        """_parse_product should handle missing availability."""
        item = {
            "itemId": "123",
            "title": "Test",
            "price": {"value": "100", "currency": "USD"},
            "itemWebUrl": "https://example.com",
        }

        product = adapter._parse_product(item)

        assert product.available_quantity is None


class TestSortOrderMapping:
    """Tests for sort order mapping."""

    @pytest.fixture()
    def adapter(self) -> EbayAdapter:
        """Create adapter for testing."""
        mock_client = AsyncMock(spec=EbayClient)
        return EbayAdapter(app_id="test", cert_id="test", client=mock_client)

    def test_map_all_sort_orders(self, adapter: EbayAdapter) -> None:
        """_map_sort_order should map all SortOrder values."""
        mappings = {
            SortOrder.RELEVANCE: "BEST_MATCH",
            SortOrder.PRICE_ASC: "price",
            SortOrder.PRICE_DESC: "-price",
            SortOrder.NEWEST: "newlyListed",
            SortOrder.BEST_SELLER: "BEST_MATCH",  # No direct equivalent
        }

        for sort_order, expected in mappings.items():
            result = adapter._map_sort_order(sort_order)
            assert result == expected
