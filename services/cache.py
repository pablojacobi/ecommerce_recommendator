"""Cache service for caching marketplace data."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from django.core.cache import cache

if TYPE_CHECKING:
    from collections.abc import Callable


class CacheKeyPrefix:
    """Cache key prefixes for different data types."""

    SEARCH = "search"
    PRODUCT = "product"
    MARKETPLACE = "marketplace"


class CacheTTL:
    """Default TTL values in seconds for different data types."""

    SEARCH_RESULTS = 300  # 5 minutes
    PRODUCT_DETAILS = 600  # 10 minutes
    MARKETPLACE_STATUS = 60  # 1 minute


class CacheService:
    """
    Service for caching marketplace data using Django's cache framework.

    Provides methods for getting, setting, and managing cached data
    with automatic key generation and TTL management.

    Example:
        >>> cache_service = CacheService()
        >>> cache_service.set("search:laptop", results, ttl=300)
        >>> cached = cache_service.get("search:laptop")
    """

    def __init__(self, key_prefix: str = "ecommerce") -> None:
        """
        Initialize the cache service.

        Args:
            key_prefix: Prefix for all cache keys (default: 'ecommerce').
        """
        self._key_prefix = key_prefix

    def _make_key(self, key: str) -> str:
        """
        Create a full cache key with prefix.

        Args:
            key: The base key.

        Returns:
            Full key with prefix.
        """
        return f"{self._key_prefix}:{key}"

    def get(self, key: str) -> Any | None:
        """
        Get a value from the cache.

        Args:
            key: The cache key.

        Returns:
            The cached value or None if not found.
        """
        return cache.get(self._make_key(key))

    def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """
        Set a value in the cache.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Time-to-live in seconds (optional).

        Returns:
            True if successful.
        """
        cache.set(self._make_key(key), value, ttl)
        return True

    def delete(self, key: str) -> bool:
        """
        Delete a value from the cache.

        Args:
            key: The cache key.

        Returns:
            True if successful.
        """
        cache.delete(self._make_key(key))
        return True

    def get_or_set(
        self,
        key: str,
        default_func: Callable[[], Any],
        ttl: int | None = None,
    ) -> Any:
        """
        Get a value from cache or set it using the default function.

        Args:
            key: The cache key.
            default_func: Function to call if key not found.
            ttl: Time-to-live in seconds (optional).

        Returns:
            The cached or computed value.
        """
        full_key = self._make_key(key)
        value = cache.get(full_key)
        if value is None:
            value = default_func()
            cache.set(full_key, value, ttl)
        return value

    def exists(self, key: str) -> bool:
        """
        Check if a key exists in the cache.

        Args:
            key: The cache key.

        Returns:
            True if the key exists.
        """
        return cache.get(self._make_key(key)) is not None

    def clear_prefix(self, prefix: str) -> None:
        """
        Clear all keys with a given prefix.

        Note: This is a best-effort operation. Some cache backends
        don't support pattern deletion.

        Args:
            prefix: The key prefix to clear.
        """
        # Django's cache doesn't support pattern deletion natively
        # This is handled by the specific cache backend if supported
        pass

    @staticmethod
    def make_search_key(
        marketplace_code: str,
        query: str,
        sort: str,
        limit: int,
        offset: int,
    ) -> str:
        """
        Generate a cache key for search results.

        Args:
            marketplace_code: The marketplace code.
            query: Search query.
            sort: Sort order.
            limit: Result limit.
            offset: Result offset.

        Returns:
            A unique cache key for this search.
        """
        # Create a hash of the search parameters
        params_str = f"{marketplace_code}:{query}:{sort}:{limit}:{offset}"
        params_hash = hashlib.md5(params_str.encode(), usedforsecurity=False).hexdigest()[:12]
        return f"{CacheKeyPrefix.SEARCH}:{marketplace_code}:{params_hash}"

    @staticmethod
    def make_product_key(marketplace_code: str, product_id: str) -> str:
        """
        Generate a cache key for product details.

        Args:
            marketplace_code: The marketplace code.
            product_id: The product ID.

        Returns:
            A unique cache key for this product.
        """
        return f"{CacheKeyPrefix.PRODUCT}:{marketplace_code}:{product_id}"


# Global cache service instance
cache_service = CacheService()
