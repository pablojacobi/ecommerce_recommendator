"""Branch-coverage tests for MercadoLibre client OAuth token handling.

These tests exercise the credentialed code paths of ``_ensure_access_token``
and the ``Authorization`` header branch of ``_make_request`` that are only
reachable when ``app_id`` and ``client_secret`` are configured.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.result import Success
from services.marketplaces.mercadolibre.client import MercadoLibreClient


class TestEnsureAccessToken:
    """Cover _ensure_access_token branches when credentials are present."""

    @pytest.fixture()
    def client(self) -> MercadoLibreClient:
        """Create a client with credentials so the auth branch is taken."""
        return MercadoLibreClient("MLC", app_id="app-id", client_secret="secret")

    @pytest.mark.asyncio
    async def test_returns_cached_token_when_still_valid(self, client: MercadoLibreClient) -> None:
        """A cached, non-expired token is returned without any HTTP call."""
        client._access_token = "cached-token"
        client._token_expires_at = time.time() + 10_000

        token = await client._ensure_access_token()

        assert token == "cached-token"

    @pytest.mark.asyncio
    async def test_fetches_new_token_on_success(self, client: MercadoLibreClient) -> None:
        """A 200 response stores and returns a freshly fetched token."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-token",
            "expires_in": 3600,
        }

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            token = await client._ensure_access_token()

        assert token == "new-token"
        assert client._access_token == "new-token"

    @pytest.mark.asyncio
    async def test_returns_none_on_non_200(self, client: MercadoLibreClient) -> None:
        """A non-200 token response returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.return_value = mock_response
            mock_get_client.return_value = mock_http

            token = await client._ensure_access_token()

        assert token is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, client: MercadoLibreClient) -> None:
        """An exception during token fetch is swallowed and returns None."""
        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.post.side_effect = RuntimeError("boom")
            mock_get_client.return_value = mock_http

            token = await client._ensure_access_token()

        assert token is None


class TestMakeRequestAuthorizationHeader:
    """Cover the Authorization header branch of _make_request."""

    @pytest.mark.asyncio
    async def test_authorization_header_set_when_token_available(self) -> None:
        """A valid access token adds a Bearer Authorization header."""
        client = MercadoLibreClient("MLC", app_id="app-id", client_secret="secret")
        client._access_token = "cached-token"
        client._token_expires_at = time.time() + 10_000

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": [], "paging": {"total": 0}}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop")

        assert isinstance(result, Success)
        headers = mock_http.request.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer cached-token"
