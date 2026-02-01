"""eBay marketplace adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from core.result import Failure, Result, failure, success
from services.marketplaces.base import ProductResult, SearchResult, SortOrder
from services.marketplaces.ebay.client import EBAY_MARKETPLACES, EbayClient
from services.marketplaces.errors import MarketplaceError, ParseError

if TYPE_CHECKING:
    from services.marketplaces.base import SearchParams

logger = get_logger(__name__)


class EbayAdapter:
    """
    Adapter for eBay marketplace.

    Implements the MarketplaceAdapter protocol for searching and retrieving
    products from eBay's Browse API.

    Attributes:
        marketplace_id: eBay marketplace ID (e.g., 'EBAY_US').
    """

    def __init__(
        self,
        app_id: str,
        cert_id: str,
        marketplace_id: str = "EBAY_US",
        client: EbayClient | None = None,
    ) -> None:
        """
        Initialize eBay adapter.

        Args:
            app_id: eBay application ID.
            cert_id: eBay certificate ID (client secret).
            marketplace_id: eBay marketplace ID.
            client: Optional pre-configured client for testing.
        """
        self._marketplace_id = marketplace_id
        self._client = client or EbayClient(app_id, cert_id, marketplace_id)

    @property
    def marketplace_code(self) -> str:
        """Return the marketplace code."""
        return self._marketplace_id

    @property
    def marketplace_name(self) -> str:
        """Return the marketplace display name."""
        country = EBAY_MARKETPLACES.get(self._marketplace_id, "Unknown")
        return f"eBay {country}"

    async def search(
        self,
        params: SearchParams,
    ) -> Result[SearchResult, MarketplaceError]:
        """
        Search for products in eBay.

        Args:
            params: Search parameters.

        Returns:
            Result containing SearchResult or MarketplaceError.
        """
        # Convert sort order to eBay format
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
            items = data.get("itemSummaries", [])
            products = self._parse_products(items)
            total = data.get("total", len(items))
            offset = data.get("offset", 0)
            limit = data.get("limit", params.limit)

            return success(
                SearchResult(
                    products=tuple(products),
                    total_count=total,
                    has_more=(offset + limit) < total,
                    marketplace_code=self._marketplace_id,
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            logger.error(
                "Failed to parse eBay search results",
                marketplace_id=self._marketplace_id,
                error=str(e),
            )
            return failure(
                ParseError(
                    marketplace_code=self._marketplace_id,
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
            product_id: eBay item ID.

        Returns:
            Result containing ProductResult or MarketplaceError.
        """
        result = await self._client.get_item(product_id)

        if isinstance(result, Failure):
            return failure(result.error)

        try:
            product = self._parse_product(result.value)
            return success(product)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            logger.error(
                "Failed to parse eBay product",
                marketplace_id=self._marketplace_id,
                product_id=product_id,
                error=str(e),
            )
            return failure(
                ParseError(
                    marketplace_code=self._marketplace_id,
                    message="Failed to parse product",
                    details=str(e),
                )
            )

    async def healthcheck(self) -> bool:
        """
        Check if the eBay API is available.

        Returns:
            True if API is healthy, False otherwise.
        """
        return await self._client.healthcheck()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.close()

    def _map_sort_order(self, sort: SortOrder) -> str:
        """Map SortOrder enum to eBay sort string."""
        mapping = {
            SortOrder.RELEVANCE: "BEST_MATCH",
            SortOrder.PRICE_ASC: "price",
            SortOrder.PRICE_DESC: "-price",
            SortOrder.NEWEST: "newlyListed",
            SortOrder.BEST_SELLER: "BEST_MATCH",  # eBay doesn't have best seller sort
        }
        return mapping.get(sort, "BEST_MATCH")

    def _parse_products(self, items: list[dict[str, Any]]) -> list[ProductResult]:
        """Parse a list of eBay items into ProductResults."""
        products = []
        for item in items:
            try:
                product = self._parse_product(item)
                products.append(product)
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                logger.warning(
                    "Skipping unparseable product",
                    marketplace_id=self._marketplace_id,
                    item_id=item.get("itemId", "unknown"),
                    error=str(e),
                )
        return products

    def _parse_product(self, item: dict[str, Any]) -> ProductResult:
        """
        Parse an eBay item into a ProductResult.

        Args:
            item: Raw item data from eBay API.

        Returns:
            Parsed ProductResult.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If data cannot be parsed.
        """
        # Get price - eBay returns price as object with value and currency
        price_obj = item.get("price", {})
        price_value = price_obj.get("value", "0")
        currency = price_obj.get("currency", "USD")

        # Get image
        image = item.get("image", {})
        image_url = image.get("imageUrl") if image else None

        # Get shipping info
        shipping_options = item.get("shippingOptions", [])
        shipping_cost = None
        free_shipping = False

        if shipping_options:
            first_shipping = shipping_options[0]
            shipping_cost_obj = first_shipping.get("shippingCost", {})
            shipping_value = shipping_cost_obj.get("value")
            if shipping_value:
                shipping_cost = Decimal(str(shipping_value))
                free_shipping = shipping_cost == 0

        # Get seller info
        seller = item.get("seller", {})
        seller_name = seller.get("username")
        feedback_percentage = seller.get("feedbackPercentage")
        seller_rating = None
        if feedback_percentage:
            # Convert percentage to 0-5 scale
            seller_rating = (float(feedback_percentage) / 100) * 5

        # Get condition
        condition = item.get("condition", "New")
        condition_map = {
            "New": "new",
            "New with tags": "new",
            "New with box": "new",
            "New without tags": "new",
            "New other": "new",
            "Used": "used",
            "Pre-owned": "used",
            "Good": "used",
            "Very Good": "used",
            "Excellent": "used",
            "For parts or not working": "used",
            "Certified refurbished": "refurbished",
            "Seller refurbished": "refurbished",
            "Manufacturer refurbished": "refurbished",
        }
        condition = condition_map.get(condition, "new")

        # Item ID - eBay uses itemId in summaries, id in details
        item_id = item.get("itemId") or item.get("itemHref", "").split("/")[-1]

        return ProductResult(
            id=item_id,
            marketplace_code=self._marketplace_id,
            title=item["title"],
            price=Decimal(str(price_value)),
            currency=currency,
            url=item.get("itemWebUrl", item.get("itemHref", "")),
            image_url=image_url,
            seller_name=seller_name,
            seller_rating=seller_rating,
            condition=condition,
            shipping_cost=shipping_cost,
            free_shipping=free_shipping,
            available_quantity=item.get("estimatedAvailabilities", [{}])[0].get(
                "estimatedAvailableQuantity"
            )
            if item.get("estimatedAvailabilities")
            else None,
        )
