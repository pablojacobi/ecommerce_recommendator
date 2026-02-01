"""Search orchestrator for coordinating multi-marketplace searches."""

from __future__ import annotations

import asyncio

from core.logging import get_logger
from core.result import Failure, Result, Success, failure, success
from services.marketplaces.base import MarketplaceAdapter, SearchParams, SortOrder
from services.marketplaces.factory import MarketplaceFactory
from services.search.types import (
    AggregatedResult,
    EnrichedProduct,
    MarketplaceSearchResult,
    SearchRequest,
)

logger = get_logger(__name__)


class SearchOrchestratorError(Exception):
    """Error in search orchestration."""

    def __init__(self, message: str, details: str | None = None) -> None:
        """Initialize error."""
        super().__init__(message)
        self.message = message
        self.details = details


class SearchOrchestrator:
    """
    Orchestrates searches across multiple marketplaces.

    Coordinates parallel searches, aggregates results, and handles
    sorting and price comparison across marketplaces.
    """

    def __init__(
        self,
        factory: MarketplaceFactory,
        default_timeout: float = 30.0,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            factory: Factory for creating marketplace adapters.
            default_timeout: Default timeout for searches in seconds.
        """
        self._factory = factory
        self._default_timeout = default_timeout
        self._adapters: dict[str, MarketplaceAdapter] = {}

    async def search(
        self,
        request: SearchRequest,
    ) -> Result[AggregatedResult, SearchOrchestratorError]:
        """
        Execute search across multiple marketplaces.

        Args:
            request: The search request with intent and marketplaces.

        Returns:
            Result containing aggregated results or error.
        """
        if not request.marketplace_codes:
            return failure(SearchOrchestratorError("No marketplaces specified"))

        intent = request.intent

        # Build search params from intent
        params = SearchParams(
            query=intent.query,
            sort=intent.sort_order or SortOrder.RELEVANCE,
            limit=intent.limit,
            offset=0,
            min_price=intent.min_price,
            max_price=intent.max_price,
        )

        # Create adapters for requested marketplaces
        adapters = self._get_adapters(request.marketplace_codes)
        if not adapters:
            return failure(
                SearchOrchestratorError(
                    "No valid marketplaces found",
                    details=f"Requested: {request.marketplace_codes}",
                )
            )

        # Execute searches in parallel
        marketplace_results = await self._search_all(adapters, params)

        # Aggregate and sort results
        aggregated = self._aggregate_results(
            marketplace_results,
            sort_order=intent.sort_order,
            query=intent.query,
        )

        # Mark best prices
        self._mark_best_prices(aggregated.products)

        logger.info(
            "Search completed",
            query=intent.query,
            marketplaces=len(adapters),
            total_results=aggregated.total_count,
            successful=aggregated.successful_marketplaces,
        )

        return success(aggregated)

    def _get_adapters(
        self,
        marketplace_codes: tuple[str, ...],
    ) -> dict[str, MarketplaceAdapter]:
        """Get or create adapters for marketplace codes."""
        adapters: dict[str, MarketplaceAdapter] = {}

        for code in marketplace_codes:
            if code in self._adapters:
                adapters[code] = self._adapters[code]
            else:
                result = self._factory.get_adapter(code)
                if isinstance(result, Success):
                    self._adapters[code] = result.value
                    adapters[code] = result.value
                else:
                    logger.warning(
                        "Unknown marketplace code",
                        code=code,
                    )

        return adapters

    async def _search_all(
        self,
        adapters: dict[str, MarketplaceAdapter],
        params: SearchParams,
    ) -> list[MarketplaceSearchResult]:
        """Execute searches in all adapters in parallel."""
        tasks = [
            self._search_marketplace(code, adapter, params) for code, adapter in adapters.items()
        ]

        # Note: _search_marketplace always returns MarketplaceSearchResult,
        # never raises, so we can safely cast the results
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _search_marketplace(
        self,
        code: str,
        adapter: MarketplaceAdapter,
        params: SearchParams,
    ) -> MarketplaceSearchResult:
        """Search a single marketplace."""
        try:
            result = await asyncio.wait_for(
                adapter.search(params),
                timeout=self._default_timeout,
            )

            if isinstance(result, Failure):
                return MarketplaceSearchResult(
                    marketplace_code=code,
                    marketplace_name=adapter.marketplace_name,
                    error=result.error.message,
                )

            # Enrich products with marketplace info
            enriched = [
                EnrichedProduct(
                    product=product,
                    marketplace_code=code,
                    marketplace_name=adapter.marketplace_name,
                )
                for product in result.value.products
            ]

            return MarketplaceSearchResult(
                marketplace_code=code,
                marketplace_name=adapter.marketplace_name,
                products=enriched,
                total_count=result.value.total_count,
                has_more=result.value.has_more,
            )

        except TimeoutError:
            logger.warning(
                "Marketplace search timed out",
                marketplace=code,
                timeout=self._default_timeout,
            )
            return MarketplaceSearchResult(
                marketplace_code=code,
                marketplace_name=adapter.marketplace_name,
                error="Search timed out",
            )
        except Exception as e:
            logger.error(
                "Marketplace search failed",
                marketplace=code,
                error=str(e),
            )
            return MarketplaceSearchResult(
                marketplace_code=code,
                marketplace_name=adapter.marketplace_name,
                error=str(e),
            )

    def _aggregate_results(
        self,
        marketplace_results: list[MarketplaceSearchResult],
        sort_order: SortOrder | None,
        query: str,
    ) -> AggregatedResult:
        """Aggregate results from multiple marketplaces."""
        all_products: list[EnrichedProduct] = []
        total_count = 0
        has_more = False

        for result in marketplace_results:
            if result.is_success:
                all_products.extend(result.products)
                total_count += result.total_count
                has_more = has_more or result.has_more

        # Sort aggregated results
        sorted_products = self._sort_products(all_products, sort_order)

        return AggregatedResult(
            products=sorted_products,
            marketplace_results=marketplace_results,
            total_count=total_count,
            sort_order=sort_order,
            query=query,
            has_more=has_more,
        )

    def _sort_products(
        self,
        products: list[EnrichedProduct],
        sort_order: SortOrder | None,
    ) -> list[EnrichedProduct]:
        """Sort products according to sort order."""
        if not products:
            return products

        if sort_order == SortOrder.PRICE_ASC:
            return sorted(products, key=lambda p: p.product.price)
        elif sort_order == SortOrder.PRICE_DESC:
            return sorted(products, key=lambda p: p.product.price, reverse=True)
        elif sort_order == SortOrder.NEWEST:
            # For newest, maintain marketplace order (APIs already sort by date)
            return products
        elif sort_order == SortOrder.BEST_SELLER:
            # Sort by seller rating as proxy for popularity
            return sorted(
                products,
                key=lambda p: p.product.seller_rating or 0,
                reverse=True,
            )
        else:
            # RELEVANCE or None: interleave results from different marketplaces
            return self._interleave_results(products)

    def _interleave_results(
        self,
        products: list[EnrichedProduct],
    ) -> list[EnrichedProduct]:
        """Interleave products from different marketplaces for fair display."""
        if not products:
            return products

        # Group by marketplace
        by_marketplace: dict[str, list[EnrichedProduct]] = {}
        for product in products:
            code = product.marketplace_code
            if code not in by_marketplace:
                by_marketplace[code] = []
            by_marketplace[code].append(product)

        # Interleave
        interleaved: list[EnrichedProduct] = []
        marketplace_lists = list(by_marketplace.values())
        max_len = max(len(lst) for lst in marketplace_lists)

        for i in range(max_len):
            for marketplace_list in marketplace_lists:
                if i < len(marketplace_list):
                    interleaved.append(marketplace_list[i])

        return interleaved

    def _mark_best_prices(self, products: list[EnrichedProduct]) -> None:
        """Mark products with best price across marketplaces."""
        if not products:
            return

        # Sort by price to assign ranks
        sorted_by_price = sorted(products, key=lambda p: p.product.price)

        # Assign price ranks
        for rank, product in enumerate(sorted_by_price, start=1):
            product.price_rank = rank

        # Mark the cheapest as best price
        # sorted_by_price is guaranteed non-empty because we check products above
        sorted_by_price[0].is_best_price = True

    async def close(self) -> None:
        """Close all adapters."""
        for adapter in self._adapters.values():
            try:
                await adapter.close()
            except Exception as e:
                logger.error("Error closing adapter", error=str(e))
        self._adapters.clear()

    async def healthcheck(self) -> dict[str, bool]:
        """Check health of all cached adapters."""
        results: dict[str, bool] = {}
        for code, adapter in self._adapters.items():
            try:
                results[code] = await adapter.healthcheck()
            except Exception:
                results[code] = False
        return results
