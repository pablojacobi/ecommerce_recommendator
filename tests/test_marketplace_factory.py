"""Tests for marketplace factory."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from core.result import Failure, Success
from services.marketplaces.base import (
    MarketplaceAdapter,
    ProductResult,
    SearchParams,
    SearchResult,
)
from services.marketplaces.factory import AdapterNotFoundError, MarketplaceFactory

if TYPE_CHECKING:
    from core.result import Result
    from services.marketplaces.errors import MarketplaceError


class MockAdapter:
    """Mock adapter for testing."""

    def __init__(self, code: str, name: str) -> None:
        """Initialize mock adapter."""
        self._code = code
        self._name = name

    @property
    def marketplace_code(self) -> str:
        """Return marketplace code."""
        return self._code

    @property
    def marketplace_name(self) -> str:
        """Return marketplace name."""
        return self._name

    async def search(self, params: SearchParams) -> Result[SearchResult, MarketplaceError]:
        """Mock search."""
        return Success(
            SearchResult(
                products=(),
                total_count=0,
                has_more=False,
                marketplace_code=self._code,
            )
        )

    async def get_product(self, product_id: str) -> Result[ProductResult, MarketplaceError]:
        """Mock get_product."""
        return Success(
            ProductResult(
                id=product_id,
                marketplace_code=self._code,
                title="Mock Product",
                price=Decimal("100"),
                currency="USD",
                url="https://example.com",
            )
        )

    async def healthcheck(self) -> bool:
        """Mock healthcheck."""
        return True


class TestAdapterNotFoundError:
    """Tests for AdapterNotFoundError."""

    def test_error_message(self) -> None:
        """AdapterNotFoundError should have descriptive message."""
        error = AdapterNotFoundError("UNKNOWN")

        assert error.marketplace_code == "UNKNOWN"
        assert "UNKNOWN" in str(error)
        assert "No adapter registered" in str(error)


class TestMarketplaceFactory:
    """Tests for MarketplaceFactory."""

    @pytest.fixture()
    def factory(self) -> MarketplaceFactory:
        """Create a fresh factory for each test."""
        return MarketplaceFactory()

    @pytest.fixture()
    def ebay_adapter(self) -> MockAdapter:
        """Create mock eBay adapter."""
        return MockAdapter("EBAY_US", "eBay USA")

    @pytest.fixture()
    def meli_adapter(self) -> MockAdapter:
        """Create mock MercadoLibre adapter."""
        return MockAdapter("MLC", "MercadoLibre Chile")

    def test_register_adapter(self, factory: MarketplaceFactory, ebay_adapter: MockAdapter) -> None:
        """Factory should register adapters."""
        factory.register("EBAY_US", ebay_adapter)

        assert factory.is_registered("EBAY_US")
        assert factory.adapter_count == 1

    def test_register_empty_code_raises(
        self, factory: MarketplaceFactory, ebay_adapter: MockAdapter
    ) -> None:
        """Factory should reject empty marketplace code."""
        with pytest.raises(ValueError, match="cannot be empty"):
            factory.register("", ebay_adapter)

    def test_get_adapter_success(
        self, factory: MarketplaceFactory, ebay_adapter: MockAdapter
    ) -> None:
        """Factory should return registered adapter."""
        factory.register("EBAY_US", ebay_adapter)

        result = factory.get_adapter("EBAY_US")

        assert isinstance(result, Success)
        assert result.value == ebay_adapter

    def test_get_adapter_not_found(self, factory: MarketplaceFactory) -> None:
        """Factory should return Failure for unknown adapter."""
        result = factory.get_adapter("UNKNOWN")

        assert isinstance(result, Failure)
        assert isinstance(result.error, AdapterNotFoundError)
        assert result.error.marketplace_code == "UNKNOWN"

    def test_get_adapters_mixed(
        self,
        factory: MarketplaceFactory,
        ebay_adapter: MockAdapter,
    ) -> None:
        """Factory should return dict of results for multiple codes."""
        factory.register("EBAY_US", ebay_adapter)

        results = factory.get_adapters(["EBAY_US", "UNKNOWN"])

        assert isinstance(results["EBAY_US"], Success)
        assert isinstance(results["UNKNOWN"], Failure)

    def test_get_all_adapters(
        self,
        factory: MarketplaceFactory,
        ebay_adapter: MockAdapter,
        meli_adapter: MockAdapter,
    ) -> None:
        """Factory should return all registered adapters."""
        factory.register("EBAY_US", ebay_adapter)
        factory.register("MLC", meli_adapter)

        adapters = factory.get_all_adapters()

        assert len(adapters) == 2
        assert "EBAY_US" in adapters
        assert "MLC" in adapters

    def test_unregister_existing(
        self, factory: MarketplaceFactory, ebay_adapter: MockAdapter
    ) -> None:
        """Factory should unregister existing adapter."""
        factory.register("EBAY_US", ebay_adapter)

        result = factory.unregister("EBAY_US")

        assert result is True
        assert not factory.is_registered("EBAY_US")

    def test_unregister_nonexistent(self, factory: MarketplaceFactory) -> None:
        """Factory should return False for nonexistent adapter."""
        result = factory.unregister("UNKNOWN")

        assert result is False

    def test_is_registered(self, factory: MarketplaceFactory, ebay_adapter: MockAdapter) -> None:
        """Factory should report registration status."""
        assert not factory.is_registered("EBAY_US")

        factory.register("EBAY_US", ebay_adapter)

        assert factory.is_registered("EBAY_US")

    def test_registered_codes(
        self,
        factory: MarketplaceFactory,
        ebay_adapter: MockAdapter,
        meli_adapter: MockAdapter,
    ) -> None:
        """Factory should return list of registered codes."""
        factory.register("EBAY_US", ebay_adapter)
        factory.register("MLC", meli_adapter)

        codes = factory.registered_codes

        assert "EBAY_US" in codes
        assert "MLC" in codes

    def test_adapter_count(
        self,
        factory: MarketplaceFactory,
        ebay_adapter: MockAdapter,
        meli_adapter: MockAdapter,
    ) -> None:
        """Factory should return correct adapter count."""
        assert factory.adapter_count == 0

        factory.register("EBAY_US", ebay_adapter)
        assert factory.adapter_count == 1

        factory.register("MLC", meli_adapter)
        assert factory.adapter_count == 2

    def test_clear(
        self,
        factory: MarketplaceFactory,
        ebay_adapter: MockAdapter,
        meli_adapter: MockAdapter,
    ) -> None:
        """Factory should clear all adapters."""
        factory.register("EBAY_US", ebay_adapter)
        factory.register("MLC", meli_adapter)

        factory.clear()

        assert factory.adapter_count == 0
        assert not factory.is_registered("EBAY_US")
        assert not factory.is_registered("MLC")


class TestMockAdapterProtocol:
    """Tests to verify MockAdapter implements MarketplaceAdapter protocol."""

    def test_mock_adapter_is_marketplace_adapter(self) -> None:
        """MockAdapter should implement MarketplaceAdapter protocol."""
        adapter = MockAdapter("TEST", "Test Marketplace")

        assert isinstance(adapter, MarketplaceAdapter)
