"""Factory for creating marketplace adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.result import Failure, Success

if TYPE_CHECKING:
    from core.result import Result
    from services.marketplaces.base import MarketplaceAdapter


class AdapterNotFoundError(Exception):
    """Raised when a marketplace adapter is not found."""

    def __init__(self, marketplace_code: str) -> None:
        """Initialize with the marketplace code."""
        self.marketplace_code = marketplace_code
        super().__init__(f"No adapter registered for marketplace: {marketplace_code}")


class MarketplaceFactory:
    """
    Factory for creating and managing marketplace adapters.

    Uses a registry pattern to allow dynamic registration of adapters.
    Adapters are registered by their marketplace code and can be
    retrieved individually or in bulk.

    Example:
        >>> factory = MarketplaceFactory()
        >>> factory.register("EBAY_US", EbayAdapter())
        >>> adapter = factory.get_adapter("EBAY_US")
    """

    def __init__(self) -> None:
        """Initialize the factory with an empty registry."""
        self._adapters: dict[str, MarketplaceAdapter] = {}

    def register(self, marketplace_code: str, adapter: MarketplaceAdapter) -> None:
        """
        Register an adapter for a marketplace.

        Args:
            marketplace_code: Unique code for the marketplace.
            adapter: The adapter instance to register.

        Raises:
            ValueError: If marketplace_code is empty.
        """
        if not marketplace_code:
            msg = "marketplace_code cannot be empty"
            raise ValueError(msg)
        self._adapters[marketplace_code] = adapter

    def unregister(self, marketplace_code: str) -> bool:
        """
        Unregister an adapter.

        Args:
            marketplace_code: Code of the marketplace to unregister.

        Returns:
            True if an adapter was unregistered, False if not found.
        """
        if marketplace_code in self._adapters:
            del self._adapters[marketplace_code]
            return True
        return False

    def get_adapter(
        self,
        marketplace_code: str,
    ) -> Result[MarketplaceAdapter, AdapterNotFoundError]:
        """
        Get an adapter by marketplace code.

        Args:
            marketplace_code: Code of the marketplace.

        Returns:
            Result containing the adapter or AdapterNotFoundError.
        """
        adapter = self._adapters.get(marketplace_code)
        if adapter is None:
            return Failure(AdapterNotFoundError(marketplace_code))
        return Success(adapter)

    def get_adapters(
        self,
        marketplace_codes: list[str],
    ) -> dict[str, Result[MarketplaceAdapter, AdapterNotFoundError]]:
        """
        Get multiple adapters by their codes.

        Args:
            marketplace_codes: List of marketplace codes.

        Returns:
            Dictionary mapping codes to Results (success or failure for each).
        """
        return {code: self.get_adapter(code) for code in marketplace_codes}

    def get_all_adapters(self) -> dict[str, MarketplaceAdapter]:
        """
        Get all registered adapters.

        Returns:
            Dictionary mapping marketplace codes to adapters.
        """
        return dict(self._adapters)

    def is_registered(self, marketplace_code: str) -> bool:
        """
        Check if a marketplace is registered.

        Args:
            marketplace_code: Code of the marketplace.

        Returns:
            True if registered, False otherwise.
        """
        return marketplace_code in self._adapters

    @property
    def registered_codes(self) -> list[str]:
        """Return list of all registered marketplace codes."""
        return list(self._adapters.keys())

    @property
    def adapter_count(self) -> int:
        """Return the number of registered adapters."""
        return len(self._adapters)

    def clear(self) -> None:
        """Remove all registered adapters."""
        self._adapters.clear()
