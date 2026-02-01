"""Tests for MercadoLibre HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.result import Failure, Success
from services.marketplaces.errors import ErrorCode
from services.marketplaces.mercadolibre.client import (
    DEFAULT_TIMEOUT,
    MELI_SITES,
    MercadoLibreClient,
)


class TestMeliSites:
    """Tests for MELI_SITES constant."""

    def test_meli_sites_contains_expected_countries(self) -> None:
        """MELI_SITES should contain all expected country codes."""
        assert "MLA" in MELI_SITES  # Argentina
        assert "MLB" in MELI_SITES  # Brasil
        assert "MLC" in MELI_SITES  # Chile
        assert "MLM" in MELI_SITES  # México
        assert "MCO" in MELI_SITES  # Colombia
        assert "MPE" in MELI_SITES  # Perú
        assert "MLU" in MELI_SITES  # Uruguay

    def test_meli_sites_values_are_country_names(self) -> None:
        """MELI_SITES values should be country names."""
        assert MELI_SITES["MLC"] == "Chile"
        assert MELI_SITES["MLA"] == "Argentina"


class TestMercadoLibreClientInit:
    """Tests for MercadoLibreClient initialization."""

    def test_init_with_valid_site_id(self) -> None:
        """Client can be initialized with valid site ID."""
        client = MercadoLibreClient("MLC")

        assert client.site_id == "MLC"
        assert client.timeout == DEFAULT_TIMEOUT
        assert client.marketplace_code == "MLC"

    def test_init_with_custom_timeout(self) -> None:
        """Client can be initialized with custom timeout."""
        client = MercadoLibreClient("MLC", timeout=60.0)

        assert client.timeout == 60.0

    def test_init_with_invalid_site_id_raises(self) -> None:
        """Client should raise ValueError for invalid site ID."""
        with pytest.raises(ValueError, match="Invalid site_id"):
            MercadoLibreClient("INVALID")


class TestMercadoLibreClientRequests:
    """Tests for MercadoLibreClient HTTP requests."""

    @pytest.fixture()
    def client(self) -> MercadoLibreClient:
        """Create a client for testing."""
        return MercadoLibreClient("MLC")

    @pytest.fixture()
    def mock_response(self) -> MagicMock:
        """Create a mock HTTP response."""
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"results": [], "paging": {"total": 0}}
        response.text = ""
        return response

    @pytest.mark.asyncio
    async def test_search_success(self, client: MercadoLibreClient) -> None:
        """search should return Success with data on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [{"id": "MLC123", "title": "Test"}],
            "paging": {"total": 1, "offset": 0, "limit": 20},
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Success)
            assert result.value["paging"]["total"] == 1

    @pytest.mark.asyncio
    async def test_search_with_price_filters(self, client: MercadoLibreClient) -> None:
        """search should include price filters in request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(
                query="laptop",
                min_price=100.0,
                max_price=500.0,
            )

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["price"] == "100.0-500.0"

    @pytest.mark.asyncio
    async def test_search_with_min_price_only(self, client: MercadoLibreClient) -> None:
        """search should handle min_price only."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="laptop", min_price=100.0)

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["price"] == "100.0-*"

    @pytest.mark.asyncio
    async def test_search_with_max_price_only(self, client: MercadoLibreClient) -> None:
        """search should handle max_price only."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="laptop", max_price=500.0)

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["price"] == "*-500.0"

    @pytest.mark.asyncio
    async def test_search_rate_limit(self, client: MercadoLibreClient) -> None:
        """search should return RateLimitError on 429."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "30"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.RATE_LIMIT
            assert result.error.retry_after == 30

    @pytest.mark.asyncio
    async def test_search_rate_limit_no_retry_after(self, client: MercadoLibreClient) -> None:
        """search should default to 60s retry when no Retry-After header."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.retry_after == 60

    @pytest.mark.asyncio
    async def test_search_api_error(self, client: MercadoLibreClient) -> None:
        """search should return NetworkError on API error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_search_parse_error(self, client: MercadoLibreClient) -> None:
        """search should return ParseError on invalid JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.PARSE

    @pytest.mark.asyncio
    async def test_search_timeout(self, client: MercadoLibreClient) -> None:
        """search should return NetworkError on timeout."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.side_effect = httpx.TimeoutException("Timeout")
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK
            assert "timeout" in result.error.message.lower()

    @pytest.mark.asyncio
    async def test_search_request_error(self, client: MercadoLibreClient) -> None:
        """search should return NetworkError on request error."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_get_item_success(self, client: MercadoLibreClient) -> None:
        """get_item should return Success with item data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "MLC123",
            "title": "Test Product",
            "price": 100,
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.get_item("MLC123")

            assert isinstance(result, Success)
            assert result.value["id"] == "MLC123"

    @pytest.mark.asyncio
    async def test_healthcheck_success(self, client: MercadoLibreClient) -> None:
        """healthcheck should return True when API is available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "MLC"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.healthcheck()

            assert result is True

    @pytest.mark.asyncio
    async def test_healthcheck_failure(self, client: MercadoLibreClient) -> None:
        """healthcheck should return False when API is unavailable."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_http

            result = await client.healthcheck()

            assert result is False

    @pytest.mark.asyncio
    async def test_healthcheck_exception(self, client: MercadoLibreClient) -> None:
        """healthcheck should return False on any exception."""
        with patch.object(client, "_make_request") as mock_request:
            mock_request.side_effect = Exception("Unexpected error")

            result = await client.healthcheck()

            assert result is False


class TestMercadoLibreClientLifecycle:
    """Tests for client lifecycle management."""

    @pytest.mark.asyncio
    async def test_get_client_creates_new_client(self) -> None:
        """_get_client should create new client when none exists."""
        client = MercadoLibreClient("MLC")
        assert client._client is None

        http_client = await client._get_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_reuses_existing_client(self) -> None:
        """_get_client should reuse existing client."""
        client = MercadoLibreClient("MLC")

        http_client1 = await client._get_client()
        http_client2 = await client._get_client()

        assert http_client1 is http_client2
        await client.close()

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """close should close the HTTP client."""
        client = MercadoLibreClient("MLC")
        await client._get_client()  # Create client

        await client.close()

        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_when_no_client(self) -> None:
        """close should not raise when no client exists."""
        client = MercadoLibreClient("MLC")

        await client.close()  # Should not raise

        assert client._client is None


class TestSortMapping:
    """Tests for sort order mapping."""

    @pytest.mark.asyncio
    async def test_sort_mapping_relevance(self) -> None:
        """relevance sort should be mapped correctly."""
        client = MercadoLibreClient("MLC")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="test", sort="relevance")

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["sort"] == "relevance"

    @pytest.mark.asyncio
    async def test_sort_mapping_newest(self) -> None:
        """newest sort should be mapped to date_desc."""
        client = MercadoLibreClient("MLC")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="test", sort="newest")

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["sort"] == "date_desc"

    @pytest.mark.asyncio
    async def test_sort_mapping_best_seller(self) -> None:
        """best_seller sort should be mapped to sold_quantity_desc."""
        client = MercadoLibreClient("MLC")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="test", sort="best_seller")

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["sort"] == "sold_quantity_desc"

    @pytest.mark.asyncio
    async def test_sort_mapping_unknown_defaults_to_relevance(self) -> None:
        """Unknown sort should default to relevance."""
        client = MercadoLibreClient("MLC")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="test", sort="unknown_sort")

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["sort"] == "relevance"
