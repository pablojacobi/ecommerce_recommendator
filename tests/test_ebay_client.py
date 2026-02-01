"""Tests for eBay HTTP client."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from core.result import Failure, Success
from services.marketplaces.ebay.client import (
    EBAY_MARKETPLACES,
    EbayClient,
)
from services.marketplaces.errors import ErrorCode


class TestEbayMarketplaces:
    """Tests for EBAY_MARKETPLACES constant."""

    def test_ebay_marketplaces_contains_expected_ids(self) -> None:
        """EBAY_MARKETPLACES should contain expected marketplace IDs."""
        assert "EBAY_US" in EBAY_MARKETPLACES
        assert "EBAY_GB" in EBAY_MARKETPLACES
        assert "EBAY_DE" in EBAY_MARKETPLACES
        assert "EBAY_AU" in EBAY_MARKETPLACES

    def test_ebay_marketplaces_values_are_country_names(self) -> None:
        """EBAY_MARKETPLACES values should be country names."""
        assert EBAY_MARKETPLACES["EBAY_US"] == "United States"
        assert EBAY_MARKETPLACES["EBAY_GB"] == "United Kingdom"


class TestEbayClientInit:
    """Tests for EbayClient initialization."""

    def test_init_with_valid_credentials(self) -> None:
        """Client can be initialized with valid credentials."""
        client = EbayClient(
            app_id="test-app-id",
            cert_id="test-cert-id",
        )

        assert client.app_id == "test-app-id"
        assert client.cert_id == "test-cert-id"
        assert client.marketplace_id == "EBAY_US"
        assert client.marketplace_code == "EBAY_US"

    def test_init_with_custom_marketplace(self) -> None:
        """Client can be initialized with custom marketplace."""
        client = EbayClient(
            app_id="test-app-id",
            cert_id="test-cert-id",
            marketplace_id="EBAY_GB",
        )

        assert client.marketplace_id == "EBAY_GB"

    def test_init_with_empty_app_id_raises(self) -> None:
        """Client should raise ValueError for empty app_id."""
        with pytest.raises(ValueError, match="app_id and cert_id are required"):
            EbayClient(app_id="", cert_id="test-cert-id")

    def test_init_with_empty_cert_id_raises(self) -> None:
        """Client should raise ValueError for empty cert_id."""
        with pytest.raises(ValueError, match="app_id and cert_id are required"):
            EbayClient(app_id="test-app-id", cert_id="")

    def test_init_with_invalid_marketplace_raises(self) -> None:
        """Client should raise ValueError for invalid marketplace."""
        with pytest.raises(ValueError, match="Invalid marketplace_id"):
            EbayClient(
                app_id="test-app-id",
                cert_id="test-cert-id",
                marketplace_id="INVALID",
            )


class TestEbayClientTokenManagement:
    """Tests for token management."""

    @pytest.fixture()
    def client(self) -> EbayClient:
        """Create a client for testing."""
        return EbayClient(app_id="test-app-id", cert_id="test-cert-id")

    def test_is_token_valid_no_token(self, client: EbayClient) -> None:
        """_is_token_valid should return False when no token."""
        assert client._is_token_valid() is False

    def test_is_token_valid_expired(self, client: EbayClient) -> None:
        """_is_token_valid should return False when token expired."""
        client._access_token = "test-token"
        client._token_expires_at = datetime.now(UTC) - timedelta(hours=1)

        assert client._is_token_valid() is False

    def test_is_token_valid_valid(self, client: EbayClient) -> None:
        """_is_token_valid should return True when token valid."""
        client._access_token = "test-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        assert client._is_token_valid() is True

    def test_is_token_valid_near_expiry(self, client: EbayClient) -> None:
        """_is_token_valid should return False when token near expiry."""
        client._access_token = "test-token"
        # Token expires in 30 seconds, but we have 60 second buffer
        client._token_expires_at = datetime.now(UTC) + timedelta(seconds=30)

        assert client._is_token_valid() is False


class TestEbayClientAuth:
    """Tests for OAuth authentication."""

    @pytest.fixture()
    def client(self) -> EbayClient:
        """Create a client for testing."""
        return EbayClient(app_id="test-app-id", cert_id="test-cert-id")

    @pytest.mark.asyncio
    async def test_get_access_token_returns_cached(self, client: EbayClient) -> None:
        """_get_access_token should return cached token if valid."""
        client._access_token = "cached-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        result = await client._get_access_token()

        assert isinstance(result, Success)
        assert result.value == "cached-token"

    @pytest.mark.asyncio
    async def test_get_access_token_fetches_new(self, client: EbayClient) -> None:
        """_get_access_token should fetch new token when needed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 7200,
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client._get_access_token()

            assert isinstance(result, Success)
            assert result.value == "new-token"
            assert client._access_token == "new-token"

    @pytest.mark.asyncio
    async def test_get_access_token_auth_failure(self, client: EbayClient) -> None:
        """_get_access_token should return AuthenticationError on 401."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client._get_access_token()

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.AUTHENTICATION

    @pytest.mark.asyncio
    async def test_get_access_token_server_error(self, client: EbayClient) -> None:
        """_get_access_token should return NetworkError on server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client._get_access_token()

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_get_access_token_timeout(self, client: EbayClient) -> None:
        """_get_access_token should return NetworkError on timeout."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = httpx.TimeoutException("Timeout")
            mock_get_client.return_value = mock_http

            result = await client._get_access_token()

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_get_access_token_request_error(self, client: EbayClient) -> None:
        """_get_access_token should return NetworkError on request error."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_http

            result = await client._get_access_token()

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_get_access_token_parse_error(self, client: EbayClient) -> None:
        """_get_access_token should return ParseError on invalid response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"invalid": "response"}  # Missing access_token

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client._get_access_token()

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.PARSE


class TestEbayClientSearch:
    """Tests for search method."""

    @pytest.fixture()
    def client(self) -> EbayClient:
        """Create a client for testing."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")
        client._access_token = "test-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        return client

    @pytest.mark.asyncio
    async def test_search_success(self, client: EbayClient) -> None:
        """search should return Success with data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "itemSummaries": [{"itemId": "123"}],
            "total": 1,
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Success)
            assert result.value["total"] == 1

    @pytest.mark.asyncio
    async def test_search_with_price_filters(self, client: EbayClient) -> None:
        """search should include price filters."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"itemSummaries": [], "total": 0}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="laptop", min_price=100, max_price=500)

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert "filter" in params
            assert "100" in params["filter"]
            assert "500" in params["filter"]

    @pytest.mark.asyncio
    async def test_search_with_min_price_only(self, client: EbayClient) -> None:
        """search should handle min_price only."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"itemSummaries": [], "total": 0}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="laptop", min_price=100)

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["filter"] == "price:[100..]"

    @pytest.mark.asyncio
    async def test_search_with_max_price_only(self, client: EbayClient) -> None:
        """search should handle max_price only."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"itemSummaries": [], "total": 0}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            await client.search(query="laptop", max_price=500)

            call_args = mock_http.request.call_args
            params = call_args.kwargs["params"]
            assert params["filter"] == "price:[..500]"

    @pytest.mark.asyncio
    async def test_search_rate_limit(self, client: EbayClient) -> None:
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
    async def test_search_rate_limit_no_header(self, client: EbayClient) -> None:
        """search should default to 60s when no Retry-After header."""
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
    async def test_search_auth_error_invalidates_token(self, client: EbayClient) -> None:
        """search should invalidate token on 401."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.AUTHENTICATION
            assert client._access_token is None

    @pytest.mark.asyncio
    async def test_search_api_error(self, client: EbayClient) -> None:
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
    async def test_search_parse_error(self, client: EbayClient) -> None:
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
    async def test_search_timeout(self, client: EbayClient) -> None:
        """search should return NetworkError on timeout."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.side_effect = httpx.TimeoutException("Timeout")
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_search_request_error(self, client: EbayClient) -> None:
        """search should return NetworkError on request error."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK


class TestEbayClientGetItem:
    """Tests for get_item method."""

    @pytest.fixture()
    def client(self) -> EbayClient:
        """Create a client for testing."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")
        client._access_token = "test-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)
        return client

    @pytest.mark.asyncio
    async def test_get_item_success(self, client: EbayClient) -> None:
        """get_item should return Success with item data."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"itemId": "123", "title": "Test Item"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.get_item("123")

            assert isinstance(result, Success)
            assert result.value["itemId"] == "123"


class TestEbayClientHealthcheck:
    """Tests for healthcheck method."""

    @pytest.mark.asyncio
    async def test_healthcheck_success(self) -> None:
        """healthcheck should return True when auth succeeds."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.healthcheck()

            assert result is True

    @pytest.mark.asyncio
    async def test_healthcheck_failure(self) -> None:
        """healthcheck should return False when auth fails."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_http

            result = await client.healthcheck()

            assert result is False

    @pytest.mark.asyncio
    async def test_healthcheck_exception(self) -> None:
        """healthcheck should return False on any exception."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        with patch.object(client, "_get_access_token") as mock_get_token:
            mock_get_token.side_effect = Exception("Unexpected error")

            result = await client.healthcheck()

            assert result is False


class TestEbayClientLifecycle:
    """Tests for client lifecycle management."""

    @pytest.mark.asyncio
    async def test_get_client_creates_new_client(self) -> None:
        """_get_client should create new client when none exists."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")
        assert client._client is None

        http_client = await client._get_client()

        assert http_client is not None
        assert isinstance(http_client, httpx.AsyncClient)
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_recreates_closed_client(self) -> None:
        """_get_client should recreate client when closed."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        # Create and close the client
        first_client = await client._get_client()
        await first_client.aclose()
        assert first_client.is_closed

        # Should create new client since old one is closed
        second_client = await client._get_client()

        assert second_client is not None
        assert not second_client.is_closed
        # They should be different objects
        assert first_client is not second_client
        await client.close()

    @pytest.mark.asyncio
    async def test_get_client_reuses_open_client(self) -> None:
        """_get_client should reuse existing open client."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        first_client = await client._get_client()
        second_client = await client._get_client()

        # Should be the same instance
        assert first_client is second_client
        await client.close()

    @pytest.mark.asyncio
    async def test_close_closes_client(self) -> None:
        """close should close the HTTP client."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")
        await client._get_client()

        await client.close()

        assert client._client is None

    @pytest.mark.asyncio
    async def test_close_when_no_client(self) -> None:
        """close should not raise when no client exists."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        await client.close()  # Should not raise

        assert client._client is None


class TestEbayClientAuthWithNoToken:
    """Test _make_request when token fetch fails."""

    @pytest.mark.asyncio
    async def test_make_request_fails_when_token_fails(self) -> None:
        """_make_request should return failure when token fetch fails."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = httpx.RequestError("Connection failed")
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

            assert isinstance(result, Failure)
            assert result.error.code == ErrorCode.NETWORK
