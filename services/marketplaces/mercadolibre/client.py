"""HTTP client for MercadoLibre API."""

from __future__ import annotations

import time
from typing import Any

import httpx

from core.logging import get_logger
from core.result import Result, failure, success
from services.marketplaces.errors import (
    AuthenticationError,
    MarketplaceError,
    NetworkError,
    ParseError,
    RateLimitError,
)

logger = get_logger(__name__)

# MercadoLibre site IDs by country
MELI_SITES: dict[str, str] = {
    "MLA": "Argentina",
    "MLB": "Brasil",
    "MLC": "Chile",
    "MLM": "México",
    "MCO": "Colombia",
    "MPE": "Perú",
    "MLU": "Uruguay",
    "MLV": "Venezuela",
    "MEC": "Ecuador",
    "MBO": "Bolivia",
    "MPY": "Paraguay",
    "MCR": "Costa Rica",
    "MPA": "Panamá",
    "MRD": "República Dominicana",
    "MGT": "Guatemala",
    "MHN": "Honduras",
    "MSV": "El Salvador",
    "MNI": "Nicaragua",
}

# Default timeout for API requests
DEFAULT_TIMEOUT = 30.0
# Base URL for MercadoLibre API
BASE_URL = "https://api.mercadolibre.com"


class MercadoLibreClient:
    """
    HTTP client for MercadoLibre API.

    Handles all HTTP communication with MercadoLibre's API,
    including retry logic and error handling.

    Attributes:
        site_id: MercadoLibre site ID (e.g., 'MLC' for Chile).
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        site_id: str,
        app_id: str | None = None,
        client_secret: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Initialize MercadoLibre client.

        Args:
            site_id: MercadoLibre site ID (e.g., 'MLC', 'MLA').
            app_id: MercadoLibre App ID for authentication.
            client_secret: MercadoLibre Client Secret for authentication.
            timeout: Request timeout in seconds.

        Raises:
            ValueError: If site_id is not valid.
        """
        if site_id not in MELI_SITES:
            msg = f"Invalid site_id: {site_id}. Must be one of {list(MELI_SITES.keys())}"
            raise ValueError(msg)

        self.site_id = site_id
        self.app_id = app_id
        self.client_secret = client_secret
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    @property
    def marketplace_code(self) -> str:
        """Return the marketplace code."""
        return self.site_id

    @property
    def _has_credentials(self) -> bool:
        """Check if we have credentials for authentication."""
        return bool(self.app_id and self.client_secret)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                timeout=self.timeout,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    # Use browser-like User-Agent to avoid datacenter IP blocking
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                },
            )
        return self._client

    async def _ensure_access_token(self) -> str | None:
        """Ensure we have a valid access token, refreshing if needed."""
        if not self._has_credentials:
            return None

        # Check if token is still valid (with 5 min buffer)
        if self._access_token and time.time() < (self._token_expires_at - 300):
            return self._access_token

        # Get new token using Client Credentials flow
        client = await self._get_client()

        try:
            response = await client.post(
                "/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.app_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code == 200:
                data = response.json()
                self._access_token = data.get("access_token")
                expires_in = data.get("expires_in", 21600)  # Default 6 hours
                self._token_expires_at = time.time() + expires_in
                logger.info(
                    "MercadoLibre access token obtained",
                    site_id=self.site_id,
                    expires_in=expires_in,
                )
                return self._access_token
            else:
                logger.error(
                    "Failed to get MercadoLibre access token",
                    site_id=self.site_id,
                    status_code=response.status_code,
                    response=response.text[:500],
                )
                return None

        except Exception as e:
            logger.error(
                "Error getting MercadoLibre access token",
                site_id=self.site_id,
                error=str(e),
            )
            return None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Result[dict[str, Any], MarketplaceError]:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method.
            path: API path.
            params: Query parameters.

        Returns:
            Result containing response data or MarketplaceError.
        """
        client = await self._get_client()

        # Get access token if we have credentials
        access_token = await self._ensure_access_token()

        # Build headers
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                headers=headers if headers else None,
            )

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_seconds = int(retry_after) if retry_after else 60
                logger.warning(
                    "Rate limited by MercadoLibre",
                    site_id=self.site_id,
                    retry_after=retry_seconds,
                )
                return failure(
                    RateLimitError(
                        marketplace_code=self.site_id,
                        retry_after=retry_seconds,
                    )
                )

            # Handle other errors
            if response.status_code >= 400:
                logger.error(
                    "MercadoLibre API error",
                    site_id=self.site_id,
                    status_code=response.status_code,
                    response_text=response.text[:500],
                )
                return failure(
                    NetworkError(
                        marketplace_code=self.site_id,
                        message=f"API returned status {response.status_code}",
                        details=response.text[:500],
                    )
                )

            # Parse response
            try:
                data: dict[str, Any] = response.json()
                return success(data)
            except ValueError as e:
                logger.error(
                    "Failed to parse MercadoLibre response",
                    site_id=self.site_id,
                    error=str(e),
                )
                return failure(
                    ParseError(
                        marketplace_code=self.site_id,
                        details=str(e),
                    )
                )

        except httpx.TimeoutException:
            logger.error(
                "MercadoLibre request timeout",
                site_id=self.site_id,
                path=path,
            )
            return failure(
                NetworkError(
                    marketplace_code=self.site_id,
                    message="Request timeout",
                )
            )
        except httpx.RequestError as e:
            logger.error(
                "MercadoLibre request error",
                site_id=self.site_id,
                error=str(e),
            )
            return failure(
                NetworkError(
                    marketplace_code=self.site_id,
                    message="Request failed",
                    details=str(e),
                )
            )

    async def search(
        self,
        query: str,
        sort: str = "relevance",
        limit: int = 20,
        offset: int = 0,
        min_price: float | None = None,
        max_price: float | None = None,
    ) -> Result[dict[str, Any], MarketplaceError]:
        """
        Search for products.

        Args:
            query: Search query.
            sort: Sort order (relevance, price_asc, price_desc).
            limit: Maximum results to return.
            offset: Results offset for pagination.
            min_price: Minimum price filter.
            max_price: Maximum price filter.

        Returns:
            Result containing search response or MarketplaceError.
        """
        params: dict[str, Any] = {
            "q": query,
            "limit": min(limit, 50),  # MercadoLibre max is 50
            "offset": offset,
        }

        # Map sort order to MercadoLibre format
        sort_mapping = {
            "relevance": "relevance",
            "price_asc": "price_asc",
            "price_desc": "price_desc",
            "newest": "date_desc",
            "best_seller": "sold_quantity_desc",
        }
        params["sort"] = sort_mapping.get(sort, "relevance")

        # Add price filters
        if min_price is not None:
            params["price"] = f"{min_price}-*"
        if max_price is not None:
            if min_price is not None:
                params["price"] = f"{min_price}-{max_price}"
            else:
                params["price"] = f"*-{max_price}"

        logger.info(
            "Searching MercadoLibre",
            site_id=self.site_id,
            query=query,
            params=params,
        )

        return await self._make_request(
            method="GET",
            path=f"/sites/{self.site_id}/search",
            params=params,
        )

    async def get_item(
        self,
        item_id: str,
    ) -> Result[dict[str, Any], MarketplaceError]:
        """
        Get item details.

        Args:
            item_id: MercadoLibre item ID.

        Returns:
            Result containing item data or MarketplaceError.
        """
        logger.info(
            "Getting MercadoLibre item",
            site_id=self.site_id,
            item_id=item_id,
        )

        return await self._make_request(
            method="GET",
            path=f"/items/{item_id}",
        )

    async def healthcheck(self) -> bool:
        """
        Check if the API is available.

        Returns:
            True if API is healthy, False otherwise.
        """
        try:
            result = await self._make_request(
                method="GET",
                path=f"/sites/{self.site_id}",
            )
            return result.is_success()
        except Exception:
            return False
