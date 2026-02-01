"""Tests for cache service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.cache import CacheKeyPrefix, CacheService, CacheTTL, cache_service


class TestCacheKeyPrefix:
    """Tests for CacheKeyPrefix constants."""

    def test_prefixes_exist(self) -> None:
        """CacheKeyPrefix should have expected values."""
        assert CacheKeyPrefix.SEARCH == "search"
        assert CacheKeyPrefix.PRODUCT == "product"
        assert CacheKeyPrefix.MARKETPLACE == "marketplace"


class TestCacheTTL:
    """Tests for CacheTTL constants."""

    def test_ttl_values(self) -> None:
        """CacheTTL should have reasonable values."""
        assert CacheTTL.SEARCH_RESULTS == 300  # 5 minutes
        assert CacheTTL.PRODUCT_DETAILS == 600  # 10 minutes
        assert CacheTTL.MARKETPLACE_STATUS == 60  # 1 minute


class TestCacheService:
    """Tests for CacheService."""

    @pytest.fixture()
    def service(self) -> CacheService:
        """Create a cache service for testing."""
        return CacheService(key_prefix="test")

    def test_make_key(self, service: CacheService) -> None:
        """_make_key should create prefixed key."""
        key = service._make_key("mykey")

        assert key == "test:mykey"

    @patch("services.cache.cache")
    def test_set_and_get(self, mock_cache: MagicMock, service: CacheService) -> None:
        """Should be able to set and get values."""
        mock_cache.get.return_value = "test_value"

        service.set("test_key", "test_value")
        result = service.get("test_key")

        assert result == "test_value"
        mock_cache.set.assert_called_once()
        mock_cache.get.assert_called_once_with("test:test_key")

    @patch("services.cache.cache")
    def test_get_nonexistent(self, mock_cache: MagicMock, service: CacheService) -> None:
        """get should return None for nonexistent key."""
        mock_cache.get.return_value = None

        result = service.get("nonexistent")

        assert result is None

    @patch("services.cache.cache")
    def test_set_with_ttl(self, mock_cache: MagicMock, service: CacheService) -> None:
        """set should accept TTL."""
        result = service.set("key_with_ttl", "value", ttl=60)

        assert result is True
        mock_cache.set.assert_called_once_with("test:key_with_ttl", "value", 60)

    @patch("services.cache.cache")
    def test_delete(self, mock_cache: MagicMock, service: CacheService) -> None:
        """delete should remove cached value."""
        result = service.delete("to_delete")

        assert result is True
        mock_cache.delete.assert_called_once_with("test:to_delete")

    @patch("services.cache.cache")
    def test_get_or_set_miss(self, mock_cache: MagicMock, service: CacheService) -> None:
        """get_or_set should call function on cache miss."""
        mock_cache.get.return_value = None
        call_count = 0

        def compute() -> str:
            nonlocal call_count
            call_count += 1
            return "computed_value"

        result = service.get_or_set("computed", compute)

        assert result == "computed_value"
        assert call_count == 1
        mock_cache.set.assert_called_once()

    @patch("services.cache.cache")
    def test_get_or_set_hit(self, mock_cache: MagicMock, service: CacheService) -> None:
        """get_or_set should return cached value on hit."""
        mock_cache.get.return_value = "cached_value"
        call_count = 0

        def compute() -> str:
            nonlocal call_count
            call_count += 1
            return "new_value"

        result = service.get_or_set("existing", compute)

        assert result == "cached_value"
        assert call_count == 0  # Function not called

    @patch("services.cache.cache")
    def test_exists_true(self, mock_cache: MagicMock, service: CacheService) -> None:
        """exists should return True for existing key."""
        mock_cache.get.return_value = "some_value"

        assert service.exists("exists_test") is True

    @patch("services.cache.cache")
    def test_exists_false(self, mock_cache: MagicMock, service: CacheService) -> None:
        """exists should return False for nonexistent key."""
        mock_cache.get.return_value = None

        assert service.exists("does_not_exist") is False

    def test_clear_prefix(self, service: CacheService) -> None:
        """clear_prefix should not raise."""
        # This is a no-op for most cache backends
        service.clear_prefix("some_prefix")


class TestCacheKeyGeneration:
    """Tests for static key generation methods."""

    def test_make_search_key(self) -> None:
        """make_search_key should create unique, consistent keys."""
        key1 = CacheService.make_search_key(
            marketplace_code="EBAY_US",
            query="laptop",
            sort="price_asc",
            limit=20,
            offset=0,
        )
        key2 = CacheService.make_search_key(
            marketplace_code="EBAY_US",
            query="laptop",
            sort="price_asc",
            limit=20,
            offset=0,
        )
        key3 = CacheService.make_search_key(
            marketplace_code="EBAY_US",
            query="laptop",
            sort="price_desc",  # Different sort
            limit=20,
            offset=0,
        )

        # Same params should produce same key
        assert key1 == key2
        # Different params should produce different key
        assert key1 != key3
        # Key should start with search prefix
        assert key1.startswith(f"{CacheKeyPrefix.SEARCH}:")

    def test_make_product_key(self) -> None:
        """make_product_key should create predictable keys."""
        key = CacheService.make_product_key("EBAY_US", "12345")

        assert key == f"{CacheKeyPrefix.PRODUCT}:EBAY_US:12345"


class TestGlobalCacheService:
    """Tests for global cache_service instance."""

    def test_global_instance_exists(self) -> None:
        """Global cache_service should be available."""
        assert cache_service is not None
        assert isinstance(cache_service, CacheService)

    def test_global_instance_default_prefix(self) -> None:
        """Global cache_service should have default prefix."""
        key = cache_service._make_key("test")

        assert key == "ecommerce:test"
