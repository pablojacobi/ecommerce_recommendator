"""Tests for MercadoLibre marketplace adapter."""

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
from services.marketplaces.errors import ErrorCode, NetworkError
from services.marketplaces.mercadolibre.adapter import MercadoLibreAdapter
from services.marketplaces.mercadolibre.client import MercadoLibreClient


class TestMercadoLibreAdapterInit:
    """Tests for MercadoLibreAdapter initialization."""

    def test_adapter_implements_protocol(self) -> None:
        """Adapter should implement MarketplaceAdapter protocol."""
        adapter = MercadoLibreAdapter("MLC")

        assert isinstance(adapter, MarketplaceAdapter)

    def test_marketplace_code(self) -> None:
        """marketplace_code should return site ID."""
        adapter = MercadoLibreAdapter("MLC")

        assert adapter.marketplace_code == "MLC"

    def test_marketplace_name(self) -> None:
        """marketplace_name should return formatted name."""
        adapter = MercadoLibreAdapter("MLC")

        assert adapter.marketplace_name == "MercadoLibre Chile"

    def test_marketplace_name_unknown_site(self) -> None:
        """marketplace_name should handle unknown site gracefully."""
        # Create adapter with mock client to bypass validation
        mock_client = AsyncMock(spec=MercadoLibreClient)
        adapter = MercadoLibreAdapter.__new__(MercadoLibreAdapter)
        adapter._site_id = "UNKNOWN"
        adapter._client = mock_client

        assert adapter.marketplace_name == "MercadoLibre Unknown"


class TestMercadoLibreAdapterSearch:
    """Tests for MercadoLibreAdapter search method."""

    @pytest.fixture()
    def mock_client(self) -> AsyncMock:
        """Create a mock client."""
        return AsyncMock(spec=MercadoLibreClient)

    @pytest.fixture()
    def adapter(self, mock_client: AsyncMock) -> MercadoLibreAdapter:
        """Create adapter with mock client."""
        return MercadoLibreAdapter("MLC", client=mock_client)

    @pytest.fixture()
    def sample_api_response(self) -> dict[str, Any]:
        """Create sample API response."""
        return {
            "results": [
                {
                    "id": "MLC123456",
                    "title": "Laptop Gaming Intel i7",
                    "price": 599990,
                    "currency_id": "CLP",
                    "permalink": "https://articulo.mercadolibre.cl/MLC-123456",
                    "thumbnail": "https://http2.mlstatic.com/D_123456-MLC.jpg",
                    "condition": "new",
                    "shipping": {"free_shipping": True},
                    "seller": {
                        "nickname": "TECH_STORE",
                        "seller_reputation": {
                            "transactions": {
                                "ratings": {
                                    "positive": 95,
                                    "negative": 2,
                                    "neutral": 3,
                                }
                            }
                        },
                    },
                    "available_quantity": 10,
                },
                {
                    "id": "MLC789012",
                    "title": "Laptop Basic",
                    "price": 299990,
                    "currency_id": "CLP",
                    "permalink": "https://articulo.mercadolibre.cl/MLC-789012",
                    "thumbnail": None,
                    "pictures": [{"url": "https://http2.mlstatic.com/D_789012.jpg"}],
                    "condition": "used",
                    "shipping": {"free_shipping": False},
                    "seller": {"nickname": "SELLER2"},
                    "available_quantity": 5,
                },
            ],
            "paging": {
                "total": 100,
                "offset": 0,
                "limit": 20,
            },
        }

    @pytest.mark.asyncio
    async def test_search_success(
        self,
        adapter: MercadoLibreAdapter,
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
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
        sample_api_response: dict[str, Any],
    ) -> None:
        """search should parse products with correct fields."""
        mock_client.search.return_value = Success(sample_api_response)
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        product = result.value.products[0]
        assert product.id == "MLC123456"
        assert product.title == "Laptop Gaming Intel i7"
        assert product.price == Decimal("599990")
        assert product.currency == "CLP"
        assert product.free_shipping is True
        assert product.condition == "new"
        assert product.seller_name == "TECH_STORE"
        assert product.seller_rating is not None
        assert 4.5 < product.seller_rating <= 5.0  # 95% positive

    @pytest.mark.asyncio
    async def test_search_handles_missing_thumbnail(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
        sample_api_response: dict[str, Any],
    ) -> None:
        """search should use pictures when thumbnail is missing."""
        mock_client.search.return_value = Success(sample_api_response)
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        # Second product has no thumbnail but has pictures
        assert isinstance(result, Success)
        product = result.value.products[1]
        assert product.image_url == "https://http2.mlstatic.com/D_789012.jpg"

    @pytest.mark.asyncio
    async def test_search_with_sort_order(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should pass sort order to client."""
        mock_client.search.return_value = Success(
            {"results": [], "paging": {"total": 0, "offset": 0, "limit": 20}}
        )
        params = SearchParams(query="laptop", sort=SortOrder.PRICE_ASC)

        await adapter.search(params)

        mock_client.search.assert_called_once()
        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["sort"] == "price_asc"

    @pytest.mark.asyncio
    async def test_search_with_price_filters(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should pass price filters to client."""
        mock_client.search.return_value = Success(
            {"results": [], "paging": {"total": 0, "offset": 0, "limit": 20}}
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
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should propagate client errors."""
        error = NetworkError("MLC", message="Connection failed")
        mock_client.search.return_value = Failure(error)
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_search_parse_error(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should return ParseError on invalid response."""
        mock_client.search.return_value = Success(
            {"invalid": "response"}  # Missing required fields
        )
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        # Should still succeed but with empty results
        assert isinstance(result, Success)
        assert result.value.products == ()

    @pytest.mark.asyncio
    async def test_search_parse_exception(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should return Failure when paging data causes exception."""
        # This will cause a TypeError when trying to access paging["total"]
        mock_client.search.return_value = Success({"results": [], "paging": None})
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.PARSE

    @pytest.mark.asyncio
    async def test_search_has_more_false_when_at_end(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should set has_more=False when no more results."""
        mock_client.search.return_value = Success(
            {
                "results": [
                    {
                        "id": "MLC123",
                        "title": "Test",
                        "price": 100,
                        "currency_id": "CLP",
                        "permalink": "https://example.com",
                        "shipping": {},
                        "seller": {},
                    }
                ],
                "paging": {"total": 1, "offset": 0, "limit": 20},
            }
        )
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        assert result.value.has_more is False

    @pytest.mark.asyncio
    async def test_search_skips_unparseable_products(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """search should skip products that can't be parsed."""
        mock_client.search.return_value = Success(
            {
                "results": [
                    {"invalid": "product"},  # Missing required fields
                    {
                        "id": "MLC123",
                        "title": "Valid Product",
                        "price": 100,
                        "currency_id": "CLP",
                        "permalink": "https://example.com",
                        "shipping": {},
                        "seller": {},
                    },
                ],
                "paging": {"total": 2, "offset": 0, "limit": 20},
            }
        )
        params = SearchParams(query="laptop")

        result = await adapter.search(params)

        assert isinstance(result, Success)
        assert len(result.value.products) == 1
        assert result.value.products[0].id == "MLC123"


class TestMercadoLibreAdapterGetProduct:
    """Tests for MercadoLibreAdapter get_product method."""

    @pytest.fixture()
    def mock_client(self) -> AsyncMock:
        """Create a mock client."""
        return AsyncMock(spec=MercadoLibreClient)

    @pytest.fixture()
    def adapter(self, mock_client: AsyncMock) -> MercadoLibreAdapter:
        """Create adapter with mock client."""
        return MercadoLibreAdapter("MLC", client=mock_client)

    @pytest.fixture()
    def sample_item_response(self) -> dict[str, Any]:
        """Create sample item response."""
        return {
            "id": "MLC123456",
            "title": "Laptop Gaming",
            "price": 599990,
            "currency_id": "CLP",
            "permalink": "https://articulo.mercadolibre.cl/MLC-123456",
            "thumbnail": "https://http2.mlstatic.com/D_123456.jpg",
            "condition": "new",
            "shipping": {"free_shipping": True},
            "seller": {
                "nickname": "TECH_STORE",
                "seller_reputation": {
                    "transactions": {"ratings": {"positive": 100, "negative": 0, "neutral": 0}}
                },
            },
            "available_quantity": 10,
        }

    @pytest.mark.asyncio
    async def test_get_product_success(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
        sample_item_response: dict[str, Any],
    ) -> None:
        """get_product should return ProductResult on success."""
        mock_client.get_item.return_value = Success(sample_item_response)

        result = await adapter.get_product("MLC123456")

        assert isinstance(result, Success)
        assert isinstance(result.value, ProductResult)
        assert result.value.id == "MLC123456"

    @pytest.mark.asyncio
    async def test_get_product_client_failure(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """get_product should propagate client errors."""
        error = NetworkError("MLC", message="Not found")
        mock_client.get_item.return_value = Failure(error)

        result = await adapter.get_product("MLC123456")

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_get_product_parse_error(
        self,
        adapter: MercadoLibreAdapter,
        mock_client: AsyncMock,
    ) -> None:
        """get_product should return ParseError on invalid response."""
        mock_client.get_item.return_value = Success({"invalid": "response"})

        result = await adapter.get_product("MLC123456")

        assert isinstance(result, Failure)
        assert result.error.code == ErrorCode.PARSE


class TestMercadoLibreAdapterHealthcheck:
    """Tests for MercadoLibreAdapter healthcheck method."""

    @pytest.mark.asyncio
    async def test_healthcheck_delegates_to_client(self) -> None:
        """healthcheck should delegate to client."""
        mock_client = AsyncMock(spec=MercadoLibreClient)
        mock_client.healthcheck.return_value = True
        adapter = MercadoLibreAdapter("MLC", client=mock_client)

        result = await adapter.healthcheck()

        assert result is True
        mock_client.healthcheck.assert_called_once()


class TestMercadoLibreAdapterClose:
    """Tests for MercadoLibreAdapter close method."""

    @pytest.mark.asyncio
    async def test_close_delegates_to_client(self) -> None:
        """close should delegate to client."""
        mock_client = AsyncMock(spec=MercadoLibreClient)
        adapter = MercadoLibreAdapter("MLC", client=mock_client)

        await adapter.close()

        mock_client.close.assert_called_once()


class TestProductParsing:
    """Tests for product parsing edge cases."""

    @pytest.fixture()
    def adapter(self) -> MercadoLibreAdapter:
        """Create adapter for testing."""
        mock_client = AsyncMock(spec=MercadoLibreClient)
        return MercadoLibreAdapter("MLC", client=mock_client)

    def test_parse_product_with_no_seller_rating(self, adapter: MercadoLibreAdapter) -> None:
        """_parse_product should handle missing seller rating."""
        item = {
            "id": "MLC123",
            "title": "Test",
            "price": 100,
            "currency_id": "CLP",
            "permalink": "https://example.com",
            "shipping": {},
            "seller": {},
        }

        product = adapter._parse_product(item)

        assert product.seller_rating is None

    def test_parse_product_with_zero_ratings(self, adapter: MercadoLibreAdapter) -> None:
        """_parse_product should handle zero total ratings."""
        item = {
            "id": "MLC123",
            "title": "Test",
            "price": 100,
            "currency_id": "CLP",
            "permalink": "https://example.com",
            "shipping": {},
            "seller": {
                "seller_reputation": {
                    "transactions": {"ratings": {"positive": 0, "negative": 0, "neutral": 0}}
                }
            },
        }

        product = adapter._parse_product(item)

        assert product.seller_rating is None

    def test_parse_product_condition_mapping(self, adapter: MercadoLibreAdapter) -> None:
        """_parse_product should map conditions correctly."""
        for api_condition, expected in [
            ("new", "new"),
            ("used", "used"),
            ("refurbished", "refurbished"),
            ("unknown", "new"),  # Default
        ]:
            item = {
                "id": "MLC123",
                "title": "Test",
                "price": 100,
                "currency_id": "CLP",
                "permalink": "https://example.com",
                "condition": api_condition,
                "shipping": {},
                "seller": {},
            }

            product = adapter._parse_product(item)

            assert product.condition == expected

    def test_parse_product_no_image(self, adapter: MercadoLibreAdapter) -> None:
        """_parse_product should handle missing images."""
        item = {
            "id": "MLC123",
            "title": "Test",
            "price": 100,
            "currency_id": "CLP",
            "permalink": "https://example.com",
            "shipping": {},
            "seller": {},
        }

        product = adapter._parse_product(item)

        assert product.image_url is None

    def test_parse_product_empty_pictures(self, adapter: MercadoLibreAdapter) -> None:
        """_parse_product should handle empty pictures array."""
        item = {
            "id": "MLC123",
            "title": "Test",
            "price": 100,
            "currency_id": "CLP",
            "permalink": "https://example.com",
            "thumbnail": None,
            "pictures": [],
            "shipping": {},
            "seller": {},
        }

        product = adapter._parse_product(item)

        assert product.image_url is None


class TestSortOrderMapping:
    """Tests for sort order mapping."""

    @pytest.fixture()
    def adapter(self) -> MercadoLibreAdapter:
        """Create adapter for testing."""
        mock_client = AsyncMock(spec=MercadoLibreClient)
        return MercadoLibreAdapter("MLC", client=mock_client)

    def test_map_all_sort_orders(self, adapter: MercadoLibreAdapter) -> None:
        """_map_sort_order should map all SortOrder values."""
        mappings = {
            SortOrder.RELEVANCE: "relevance",
            SortOrder.PRICE_ASC: "price_asc",
            SortOrder.PRICE_DESC: "price_desc",
            SortOrder.NEWEST: "newest",
            SortOrder.BEST_SELLER: "best_seller",
        }

        for sort_order, expected in mappings.items():
            result = adapter._map_sort_order(sort_order)
            assert result == expected
