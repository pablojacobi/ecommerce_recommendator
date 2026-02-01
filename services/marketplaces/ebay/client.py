"""HTTP client for eBay Browse API."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from core.logging import get_logger
from core.result import Failure, Result, failure, success
from services.marketplaces.errors import (
    AuthenticationError,
    MarketplaceError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = get_logger(__name__)

# eBay API endpoints
AUTH_URL = "https://api.ebay.com/identity/v1/oauth2/token"
BROWSE_API_URL = "https://api.ebay.com/buy/browse/v1"

# Default timeout for API requests
DEFAULT_TIMEOUT = 30.0

# eBay marketplace IDs
EBAY_MARKETPLACES: dict[str, str] = {
    "EBAY_US": "United States",
    "EBAY_GB": "United Kingdom",
    "EBAY_DE": "Germany",
    "EBAY_AU": "Australia",
    "EBAY_CA": "Canada",
    "EBAY_FR": "France",
    "EBAY_IT": "Italy",
    "EBAY_ES": "Spain",
}


class EbayClient:
    """
    HTTP client for eBay Browse API.

    Handles OAuth 2.0 authentication and API requests.
    Uses Client Credentials flow for public data access.

    Attributes:
        app_id: eBay application ID.
        cert_id: eBay certificate ID (client secret).
        marketplace_id: eBay marketplace ID (default: EBAY_US).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        app_id: str,
        cert_id: str,
        marketplace_id: str = "EBAY_US",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Initialize eBay client.

        Args:
            app_id: eBay application ID.
            cert_id: eBay certificate ID (client secret).
            marketplace_id: eBay marketplace ID.
            timeout: Request timeout in seconds.

        Raises:
            ValueError: If credentials are empty or marketplace_id is invalid.
        """
        if not app_id or not cert_id:
            msg = "app_id and cert_id are required"
            raise ValueError(msg)

        if marketplace_id not in EBAY_MARKETPLACES:
            valid_ids = list(EBAY_MARKETPLACES.keys())
            msg = f"Invalid marketplace_id: {marketplace_id}. Must be one of {valid_ids}"
            raise ValueError(msg)

        self.app_id = app_id
        self.cert_id = cert_id
        self.marketplace_id = marketplace_id
        self.timeout = timeout

        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None

    @property
    def marketplace_code(self) -> str:
        """Return the marketplace code."""
        return self.marketplace_id

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _is_token_valid(self) -> bool:
        """Check if current access token is valid."""
        if self._access_token is None or self._token_expires_at is None:
            return False
        # Add 60 second buffer before expiry
        return datetime.now(UTC) < (self._token_expires_at - timedelta(seconds=60))

    async def _get_access_token(self) -> Result[str, MarketplaceError]:
        """
        Get or refresh OAuth access token.

        Returns:
            Result containing access token or MarketplaceError.
        """
        if self._is_token_valid() and self._access_token is not None:
            return success(self._access_token)

        return await self._fetch_new_token()

    async def _fetch_new_token(self) -> Result[str, MarketplaceError]:
        """Fetch a new access token from eBay OAuth API."""
        client = await self._get_client()

        # Encode credentials for Basic auth
        credentials = f"{self.app_id}:{self.cert_id}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        try:
            response = await client.post(
                AUTH_URL,
                headers={
                    "Authorization": f"Basic {encoded_credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": "https://api.ebay.com/oauth/api_scope",
                },
            )
            return self._handle_token_response(response)
        except httpx.TimeoutException:
            logger.error("eBay auth request timeout")
            return failure(
                NetworkError(
                    marketplace_code=self.marketplace_id,
                    message="Authentication request timeout",
                )
            )
        except httpx.RequestError as e:
            logger.error("eBay auth request error", error=str(e))
            return failure(
                NetworkError(
                    marketplace_code=self.marketplace_id,
                    message="Authentication request failed",
                    details=str(e),
                )
            )

    def _handle_token_response(self, response: httpx.Response) -> Result[str, MarketplaceError]:
        """Handle the OAuth token response."""
        if response.status_code == 401:
            logger.error("eBay authentication failed", status_code=response.status_code)
            return failure(
                AuthenticationError(
                    marketplace_code=self.marketplace_id,
                    message="Invalid credentials",
                )
            )

        if response.status_code >= 400:
            logger.error(
                "eBay token request failed",
                status_code=response.status_code,
                response_text=response.text[:500],
            )
            return failure(
                NetworkError(
                    marketplace_code=self.marketplace_id,
                    message=f"Token request failed with status {response.status_code}",
                )
            )

        try:
            data = response.json()
            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 7200)
            self._token_expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)

            logger.info("eBay access token obtained", expires_in=expires_in)
            return success(self._access_token)
        except (KeyError, ValueError) as e:
            logger.error("Failed to parse eBay auth response", error=str(e))
            return failure(
                ParseError(
                    marketplace_code=self.marketplace_id,
                    message="Failed to parse authentication response",
                    details=str(e),
                )
            )

    async def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any], MarketplaceError]:
        """
        Make an authenticated API request.

        Args:
            method: HTTP method.
            path: API path.
            params: Query parameters.

        Returns:
            Result containing response data or MarketplaceError.
        """
        # Get access token
        token_result = await self._get_access_token()
        if isinstance(token_result, Failure):
            return failure(token_result.error)

        token = token_result.value
        client = await self._get_client()

        try:
            response = await client.request(
                method=method,
                url=f"{BROWSE_API_URL}{path}",
                params=params,
                headers={
                    "Authorization": f"Bearer {token}",
                    "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
                    "Accept": "application/json",
                },
            )
            return self._handle_api_response(response)
        except httpx.TimeoutException:
            logger.error("eBay request timeout", marketplace_id=self.marketplace_id)
            return failure(
                NetworkError(
                    marketplace_code=self.marketplace_id,
                    message="Request timeout",
                )
            )
        except httpx.RequestError as e:
            logger.error("eBay request error", marketplace_id=self.marketplace_id)
            return failure(
                NetworkError(
                    marketplace_code=self.marketplace_id,
                    message="Request failed",
                    details=str(e),
                )
            )

    def _handle_api_response(
        self, response: httpx.Response
    ) -> Result[dict[str, Any], MarketplaceError]:
        """Handle API response and convert to Result."""
        # Handle rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_seconds = int(retry_after) if retry_after else 60
            logger.warning(
                "Rate limited by eBay",
                marketplace_id=self.marketplace_id,
                retry_after=retry_seconds,
            )
            return failure(
                RateLimitError(
                    marketplace_code=self.marketplace_id,
                    retry_after=retry_seconds,
                )
            )

        # Handle auth errors (token might have expired)
        if response.status_code == 401:
            self._access_token = None
            self._token_expires_at = None
            return failure(
                AuthenticationError(
                    marketplace_code=self.marketplace_id,
                    message="Access token expired or invalid",
                )
            )

        # Handle other errors
        if response.status_code >= 400:
            logger.error(
                "eBay API error",
                marketplace_id=self.marketplace_id,
                status_code=response.status_code,
            )
            return failure(
                NetworkError(
                    marketplace_code=self.marketplace_id,
                    message=f"API returned status {response.status_code}",
                    details=response.text[:500],
                )
            )

        # Parse response
        try:
            data: dict[str, Any] = response.json()
            return success(data)
        except ValueError as e:
            logger.error("Failed to parse eBay response", error=str(e))
            return failure(ParseError(marketplace_code=self.marketplace_id))

    async def search(
        self,
        query: str,
        sort: str = "BEST_MATCH",
        limit: int = 20,
        offset: int = 0,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> Result[dict[str, Any], MarketplaceError]:
        """
        Search for items using eBay Browse API.

        Args:
            query: Search query.
            sort: Sort order (BEST_MATCH, PRICE, -PRICE, NEWLYLISTED).
            limit: Maximum results to return.
            offset: Results offset for pagination.
            min_price: Minimum price filter.
            max_price: Maximum price filter.

        Returns:
            Result containing search response or MarketplaceError.
        """
        params: dict[str, Any] = {
            "q": query,
            "limit": min(limit, 50),  # eBay max is 200, but we cap at 50
            "offset": offset,
            "sort": sort,
        }

        # Add price filters
        filters = []
        if min_price is not None:
            filters.append(f"price:[{min_price}..]")
        if max_price is not None:
            filters.append(f"price:[..{max_price}]")
        if min_price is not None and max_price is not None:
            filters = [f"price:[{min_price}..{max_price}]"]

        if filters:
            params["filter"] = ",".join(filters)

        logger.info(
            "Searching eBay",
            marketplace_id=self.marketplace_id,
            query=query,
            params=params,
        )

        return await self._make_request(
            method="GET",
            path="/item_summary/search",
            params=params,
        )

    async def get_item(
        self,
        item_id: str,
    ) -> Result[dict[str, Any], MarketplaceError]:
        """
        Get item details.

        Args:
            item_id: eBay item ID.

        Returns:
            Result containing item data or MarketplaceError.
        """
        logger.info(
            "Getting eBay item",
            marketplace_id=self.marketplace_id,
            item_id=item_id,
        )

        return await self._make_request(
            method="GET",
            path=f"/item/{item_id}",
        )

    async def healthcheck(self) -> bool:
        """
        Check if the API is available.

        Returns:
            True if API is healthy, False otherwise.
        """
        try:
            # Try to get an access token as health check
            result = await self._get_access_token()
            return result.is_success()
        except Exception:
            return False
