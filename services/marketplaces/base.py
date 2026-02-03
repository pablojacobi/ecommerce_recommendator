"""Base types and protocols for marketplace adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from decimal import Decimal

    from core.result import Result
    from services.marketplaces.errors import MarketplaceError


class SortOrder(str, Enum):
    """Sort order options for search results."""

    RELEVANCE = "relevance"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"
    NEWEST = "newest"
    BEST_SELLER = "best_seller"


@dataclass(frozen=True, slots=True)
class SearchParams:
    """
    Parameters for marketplace search.

    Attributes:
        query: Search query string.
        sort: Sort order for results.
        min_price: Minimum price filter (optional).
        max_price: Maximum price filter (optional).
        limit: Maximum number of results to return.
        offset: Number of results to skip (for pagination).
        category_id: Marketplace-specific category ID for filtering.
    """

    query: str
    sort: SortOrder = SortOrder.RELEVANCE
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    limit: int = 20
    offset: int = 0
    category_id: str | None = None

    def __post_init__(self) -> None:
        """Validate search parameters."""
        if self.limit < 1:
            msg = "limit must be at least 1"
            raise ValueError(msg)
        if self.limit > 100:
            msg = "limit cannot exceed 100"
            raise ValueError(msg)
        if self.offset < 0:
            msg = "offset cannot be negative"
            raise ValueError(msg)
        if self.min_price is not None and self.min_price < 0:
            msg = "min_price cannot be negative"
            raise ValueError(msg)
        if self.max_price is not None and self.max_price < 0:
            msg = "max_price cannot be negative"
            raise ValueError(msg)
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            msg = "min_price cannot be greater than max_price"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ProductResult:
    """
    Represents a product from a marketplace search.

    Attributes:
        id: Unique product identifier in the marketplace.
        marketplace_code: Code of the marketplace (e.g., 'EBAY_US', 'MLC').
        title: Product title.
        price: Product price.
        currency: Currency code (e.g., 'USD', 'CLP').
        url: Direct URL to the product page.
        image_url: URL of the product's main image.
        seller_name: Name of the seller (optional).
        seller_rating: Seller rating score (optional, 0-5).
        condition: Product condition (new, used, refurbished).
        shipping_cost: Shipping cost if available.
        free_shipping: Whether shipping is free.
        available_quantity: Available stock quantity.
    """

    id: str
    marketplace_code: str
    title: str
    price: Decimal
    currency: str
    url: str
    image_url: str | None = None
    seller_name: str | None = None
    seller_rating: float | None = None
    condition: str = "new"
    shipping_cost: Decimal | None = None
    free_shipping: bool = False
    available_quantity: int | None = None

    @property
    def total_price(self) -> Decimal:
        """Calculate total price including shipping."""
        if self.free_shipping or self.shipping_cost is None:
            return self.price
        return self.price + self.shipping_cost


@dataclass(frozen=True, slots=True)
class SearchResult:
    """
    Result of a marketplace search.

    Attributes:
        products: List of products found.
        total_count: Total number of results available.
        has_more: Whether more results are available.
        marketplace_code: Code of the marketplace searched.
    """

    products: tuple[ProductResult, ...]
    total_count: int
    has_more: bool
    marketplace_code: str

    @property
    def count(self) -> int:
        """Return number of products in this result."""
        return len(self.products)


@runtime_checkable
class MarketplaceAdapter(Protocol):
    """
    Protocol defining the interface for marketplace adapters.

    All marketplace implementations must conform to this protocol.
    """

    @property
    def marketplace_code(self) -> str:
        """Return the unique code for this marketplace."""
        ...

    @property
    def marketplace_name(self) -> str:
        """Return the display name for this marketplace."""
        ...

    async def search(
        self,
        params: SearchParams,
    ) -> Result[SearchResult, MarketplaceError]:
        """
        Search for products in the marketplace.

        Args:
            params: Search parameters.

        Returns:
            Result containing SearchResult on success or MarketplaceError on failure.
        """
        ...

    async def get_product(
        self,
        product_id: str,
    ) -> Result[ProductResult, MarketplaceError]:
        """
        Get details for a specific product.

        Args:
            product_id: The product's unique identifier.

        Returns:
            Result containing ProductResult on success or MarketplaceError on failure.
        """
        ...

    async def healthcheck(self) -> bool:
        """
        Check if the marketplace API is available.

        Returns:
            True if the API is healthy, False otherwise.
        """
        ...

    async def close(self) -> None:
        """
        Close the adapter and release resources.

        Should be called when the adapter is no longer needed.
        """
        ...
