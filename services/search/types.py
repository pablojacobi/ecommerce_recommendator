"""Types for search orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.gemini.types import SearchIntent
    from services.marketplaces.base import ProductResult, SortOrder


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """
    Request to search across marketplaces.

    Attributes:
        intent: The parsed search intent from user query.
        marketplace_codes: List of marketplace codes to search.
        user_id: Optional user ID for tracking.
    """

    intent: SearchIntent
    marketplace_codes: tuple[str, ...]
    user_id: str | None = None


@dataclass(slots=True)
class EnrichedProduct:
    """
    A product enriched with marketplace and comparison data.

    Attributes:
        product: The original product result.
        marketplace_code: Code of the source marketplace.
        marketplace_name: Display name of the marketplace.
        is_best_price: Whether this is the best price for similar products.
        price_rank: Rank by price among similar products (1 = cheapest).
    """

    product: ProductResult
    marketplace_code: str
    marketplace_name: str
    is_best_price: bool = False
    price_rank: int = 0


@dataclass(slots=True)
class MarketplaceSearchResult:
    """
    Search result from a single marketplace.

    Attributes:
        marketplace_code: Code of the marketplace.
        marketplace_name: Display name of the marketplace.
        products: List of products found.
        total_count: Total number of matching products.
        has_more: Whether more results are available.
        error: Error message if search failed.
    """

    marketplace_code: str
    marketplace_name: str
    products: list[EnrichedProduct] = field(default_factory=list)
    total_count: int = 0
    has_more: bool = False
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """Return True if search was successful."""
        return self.error is None


@dataclass(slots=True)
class AggregatedResult:
    """
    Aggregated search results from multiple marketplaces.

    Attributes:
        products: All products from all marketplaces, sorted.
        marketplace_results: Individual results per marketplace.
        total_count: Total products across all marketplaces.
        sort_order: The sort order applied.
        query: The original search query.
        has_more: Whether any marketplace has more results.
    """

    products: list[EnrichedProduct] = field(default_factory=list)
    marketplace_results: list[MarketplaceSearchResult] = field(default_factory=list)
    total_count: int = 0
    sort_order: SortOrder | None = None
    query: str = ""
    has_more: bool = False

    @property
    def successful_marketplaces(self) -> int:
        """Count of marketplaces that returned results."""
        return sum(1 for r in self.marketplace_results if r.is_success)

    @property
    def failed_marketplaces(self) -> list[str]:
        """List of marketplaces that failed."""
        return [r.marketplace_code for r in self.marketplace_results if not r.is_success]
