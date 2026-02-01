"""MercadoLibre marketplace adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from core.result import Failure, Result, failure, success
from services.marketplaces.base import ProductResult, SearchResult, SortOrder
from services.marketplaces.errors import MarketplaceError, ParseError
from services.marketplaces.mercadolibre.client import MELI_SITES, MercadoLibreClient

if TYPE_CHECKING:
    from services.marketplaces.base import SearchParams

logger = get_logger(__name__)


class MercadoLibreAdapter:
    """
    Adapter for MercadoLibre marketplace.

    Implements the MarketplaceAdapter protocol for searching and retrieving
    products from MercadoLibre's API.

    Attributes:
        site_id: MercadoLibre site ID (e.g., 'MLC' for Chile).
    """

    def __init__(self, site_id: str, client: MercadoLibreClient | None = None) -> None:
        """
        Initialize MercadoLibre adapter.

        Args:
            site_id: MercadoLibre site ID.
            client: Optional pre-configured client for testing.
        """
        self._site_id = site_id
        self._client = client or MercadoLibreClient(site_id)

    @property
    def marketplace_code(self) -> str:
        """Return the marketplace code."""
        return self._site_id

    @property
    def marketplace_name(self) -> str:
        """Return the marketplace display name."""
        country = MELI_SITES.get(self._site_id, "Unknown")
        return f"MercadoLibre {country}"

    async def search(
        self,
        params: SearchParams,
    ) -> Result[SearchResult, MarketplaceError]:
        """
        Search for products in MercadoLibre.

        Args:
            params: Search parameters.

        Returns:
            Result containing SearchResult or MarketplaceError.
        """
        # Convert sort order to string
        sort_str = self._map_sort_order(params.sort)

        # Convert Decimal prices to float for API
        min_price = float(params.min_price) if params.min_price is not None else None
        max_price = float(params.max_price) if params.max_price is not None else None

        # Make API call
        result = await self._client.search(
            query=params.query,
            sort=sort_str,
            limit=params.limit,
            offset=params.offset,
            min_price=min_price,
            max_price=max_price,
        )

        if isinstance(result, Failure):
            return failure(result.error)

        # Parse response
        try:
            data = result.value
            products = self._parse_products(data.get("results", []))
            paging = data.get("paging", {})
            total = paging.get("total", 0)
            offset = paging.get("offset", 0)
            limit = paging.get("limit", 0)

            return success(
                SearchResult(
                    products=tuple(products),
                    total_count=total,
                    has_more=(offset + limit) < total,
                    marketplace_code=self._site_id,
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            logger.error(
                "Failed to parse MercadoLibre search results",
                site_id=self._site_id,
                error=str(e),
            )
            return failure(
                ParseError(
                    marketplace_code=self._site_id,
                    message="Failed to parse search results",
                    details=str(e),
                )
            )

    async def get_product(
        self,
        product_id: str,
    ) -> Result[ProductResult, MarketplaceError]:
        """
        Get details for a specific product.

        Args:
            product_id: MercadoLibre item ID.

        Returns:
            Result containing ProductResult or MarketplaceError.
        """
        result = await self._client.get_item(product_id)

        if isinstance(result, Failure):
            return failure(result.error)

        try:
            product = self._parse_product(result.value)
            return success(product)
        except (KeyError, TypeError, ValueError) as e:
            logger.error(
                "Failed to parse MercadoLibre product",
                site_id=self._site_id,
                product_id=product_id,
                error=str(e),
            )
            return failure(
                ParseError(
                    marketplace_code=self._site_id,
                    message="Failed to parse product",
                    details=str(e),
                )
            )

    async def healthcheck(self) -> bool:
        """
        Check if the MercadoLibre API is available.

        Returns:
            True if API is healthy, False otherwise.
        """
        return await self._client.healthcheck()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    def _map_sort_order(self, sort: SortOrder) -> str:
        """Map SortOrder enum to MercadoLibre sort string."""
        mapping = {
            SortOrder.RELEVANCE: "relevance",
            SortOrder.PRICE_ASC: "price_asc",
            SortOrder.PRICE_DESC: "price_desc",
            SortOrder.NEWEST: "newest",
            SortOrder.BEST_SELLER: "best_seller",
        }
        return mapping.get(sort, "relevance")

    def _parse_products(self, items: list[dict[str, Any]]) -> list[ProductResult]:
        """Parse a list of MercadoLibre items into ProductResults."""
        products = []
        for item in items:
            try:
                product = self._parse_product(item)
                products.append(product)
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(
                    "Skipping unparseable product",
                    site_id=self._site_id,
                    item_id=item.get("id", "unknown"),
                    error=str(e),
                )
        return products

    def _parse_product(self, item: dict[str, Any]) -> ProductResult:
        """
        Parse a MercadoLibre item into a ProductResult.

        Args:
            item: Raw item data from MercadoLibre API.

        Returns:
            Parsed ProductResult.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If data cannot be parsed.
        """
        # Extract shipping info
        shipping = item.get("shipping", {})
        free_shipping = shipping.get("free_shipping", False)

        # Extract seller info
        seller = item.get("seller", {})
        seller_name = seller.get("nickname")

        # Get seller reputation (if available)
        seller_reputation = seller.get("seller_reputation", {})
        transactions = seller_reputation.get("transactions", {})
        ratings = transactions.get("ratings", {})

        # Calculate seller rating (0-5 scale)
        seller_rating = None
        if ratings:
            positive = ratings.get("positive", 0)
            negative = ratings.get("negative", 0)
            neutral = ratings.get("neutral", 0)
            total = positive + negative + neutral
            if total > 0:
                # Convert to 0-5 scale based on positive ratio
                seller_rating = (positive / total) * 5

        # Parse condition
        condition = item.get("condition", "new")
        condition_map = {
            "new": "new",
            "used": "used",
            "refurbished": "refurbished",
        }
        condition = condition_map.get(condition, "new")

        # Get thumbnail or main image
        image_url = item.get("thumbnail")
        if not image_url:
            pictures = item.get("pictures", [])
            if pictures:
                image_url = pictures[0].get("url")

        return ProductResult(
            id=item["id"],
            marketplace_code=self._site_id,
            title=item["title"],
            price=Decimal(str(item["price"])),
            currency=item["currency_id"],
            url=item["permalink"],
            image_url=image_url,
            seller_name=seller_name,
            seller_rating=seller_rating,
            condition=condition,
            shipping_cost=None,  # Not always available in search results
            free_shipping=free_shipping,
            available_quantity=item.get("available_quantity"),
        )
