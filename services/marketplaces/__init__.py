"""Marketplace adapters package."""

from services.marketplaces.base import (
    MarketplaceAdapter,
    ProductResult,
    SearchParams,
    SearchResult,
)
from services.marketplaces.errors import (
    AuthenticationError,
    MarketplaceError,
    NetworkError,
    ParseError,
    RateLimitError,
)
from services.marketplaces.factory import MarketplaceFactory

__all__ = [
    "AuthenticationError",
    "MarketplaceAdapter",
    "MarketplaceError",
    "MarketplaceFactory",
    "NetworkError",
    "ParseError",
    "ProductResult",
    "RateLimitError",
    "SearchParams",
    "SearchResult",
]
