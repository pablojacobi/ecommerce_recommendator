"""Search orchestrator for coordinating multi-marketplace searches."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import TYPE_CHECKING

from core.logging import get_logger
from core.result import Failure, Result, Success, failure, success
from services.marketplaces.base import MarketplaceAdapter, SearchParams, SortOrder
from services.marketplaces.factory import MarketplaceFactory
from services.search.relevance import filter_relevant_products, filter_relevant_products_async
from services.search.types import (
    AggregatedResult,
    EnrichedProduct,
    MarketplaceSearchResult,
    SearchRequest,
    TaxInfo,
)
from services.taxes import TaxBreakdown, TaxCalculationRequest, TaxCalculatorService

if TYPE_CHECKING:
    from services.marketplaces.base import ProductResult

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
        tax_calculator: TaxCalculatorService | None = None,
        gemini_client=None,
    ) -> None:
        """
        Initialize the orchestrator.

        Args:
            factory: Factory for creating marketplace adapters.
            default_timeout: Default timeout for searches in seconds.
            tax_calculator: Optional tax calculator for import tax estimation.
            gemini_client: Optional Gemini client for AI-powered filtering.
        """
        self._factory = factory
        self._default_timeout = default_timeout
        self._tax_calculator = tax_calculator or TaxCalculatorService()
        self._adapters: dict[str, MarketplaceAdapter] = {}
        self._gemini_client = gemini_client

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
        # IMPORTANT: Always use RELEVANCE (BEST_MATCH) for API call to avoid
        # getting virtual/digital items that are sorted first by price.
        # We'll sort locally after filtering irrelevant results.
        # Also request more results to have enough after filtering.
        api_limit = min(intent.limit * 3, 100)  # Request 3x more, max 100

        params = SearchParams(
            query=intent.query,
            sort=SortOrder.RELEVANCE,  # Always BEST_MATCH for API
            limit=api_limit,
            offset=0,
            min_price=intent.min_price,
            max_price=intent.max_price,
            category_id=intent.ebay_category_id,
        )

        # Store the user's desired sort criteria for later local sorting
        sort_criteria = intent.sort_criteria

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

        # Aggregate, filter, and sort results
        aggregated = await self._aggregate_results(
            marketplace_results,
            sort_criteria=sort_criteria,  # Supports N sort criteria
            query=intent.query,
            original_query=intent.original_query,
            limit=intent.limit,  # Limit to user's requested count after filtering
            min_seller_rating=intent.min_seller_rating,
        )

        # Calculate import taxes if destination country specified (use sync_to_async for DB access)
        if request.destination_country:
            from asgiref.sync import sync_to_async

            await sync_to_async(self._calculate_taxes)(
                aggregated.products, request.destination_country
            )

        # Mark best prices (consider taxes if available)
        self._mark_best_prices(aggregated.products)

        logger.info(
            "Search completed",
            query=intent.query,
            marketplaces=len(adapters),
            total_results=aggregated.total_count,
            successful=aggregated.successful_marketplaces,
            destination_country=request.destination_country,
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

    async def _aggregate_results(
        self,
        marketplace_results: list[MarketplaceSearchResult],
        sort_criteria: tuple[SortOrder, ...],
        query: str,
        original_query: str = "",
        limit: int = 20,
        min_seller_rating: float | None = None,
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

        # Filter out irrelevant products using AI if available
        original_count = len(all_products)

        if self._gemini_client is not None:
            # Use AI-powered filtering
            filtered_products = await filter_relevant_products_async(
                products=all_products,
                search_query=query,
                original_query=original_query or query,
                gemini_client=self._gemini_client,
            )
        else:
            # Fall back to basic filtering
            filtered_products = filter_relevant_products(
                products=all_products,
                search_query=query,
                original_query=original_query or query,
            )

        if len(filtered_products) < original_count:
            logger.info(
                "Filtered irrelevant products",
                original=original_count,
                filtered=len(filtered_products),
                removed=original_count - len(filtered_products),
            )

        # Filter by seller rating if specified
        if min_seller_rating is not None:
            before_rating_filter = len(filtered_products)
            filtered_products = [
                p for p in filtered_products
                if p.product.seller_rating is not None and p.product.seller_rating >= min_seller_rating
            ]
            if len(filtered_products) < before_rating_filter:
                logger.info(
                    "Filtered by seller rating",
                    min_rating=min_seller_rating,
                    before=before_rating_filter,
                    after=len(filtered_products),
                )

        # Sort aggregated results by user's preference (supports N criteria)
        sorted_products = self._sort_products(filtered_products, sort_criteria)

        # Limit to user's requested count
        limited_products = sorted_products[:limit]
        has_more = has_more or len(sorted_products) > limit

        return AggregatedResult(
            products=limited_products,
            marketplace_results=marketplace_results,
            total_count=len(filtered_products),  # Total after filter
            sort_order=sort_criteria[0] if sort_criteria else None,
            query=query,
            has_more=has_more,
        )

    def _sort_products(
        self,
        products: list[EnrichedProduct],
        sort_criteria: tuple[SortOrder, ...],
    ) -> list[EnrichedProduct]:
        """
        Sort products according to N sort criteria.
        
        Uses Python's stable sort: applies sorts in REVERSE order (last to first).
        This ensures that the primary criterion (first in list) takes precedence,
        while subsequent criteria act as tie-breakers.
        
        Example: sort_criteria = (PRICE_ASC, BEST_SELLER, NEWEST)
        - First sorts by NEWEST
        - Then by BEST_SELLER (preserving NEWEST order for ties)
        - Finally by PRICE_ASC (preserving previous order for ties)
        
        Result: Products ordered by price, with same-price items ordered by
        seller rating, and same-rating items ordered by recency.
        """
        if not products:
            return products

        result = list(products)
        
        # Apply sorts in reverse order (last criterion first)
        for sort_order in reversed(sort_criteria):
            result = self._apply_single_sort(result, sort_order)
        
        # If no criteria specified, use relevance (interleave)
        if not sort_criteria:
            result = self._interleave_results(result)
        
        return result
    
    def _apply_single_sort(
        self,
        products: list[EnrichedProduct],
        sort_order: SortOrder | None,
    ) -> list[EnrichedProduct]:
        """Apply a single sort criterion to products."""
        if sort_order == SortOrder.PRICE_ASC:
            return sorted(products, key=lambda p: p.product.price)
        elif sort_order == SortOrder.PRICE_DESC:
            return sorted(products, key=lambda p: p.product.price, reverse=True)
        elif sort_order == SortOrder.NEWEST:
            # For newest, maintain current order (APIs already sort by date)
            return products
        elif sort_order == SortOrder.BEST_SELLER:
            # Sort by seller rating (higher = better)
            return sorted(
                products,
                key=lambda p: p.product.seller_rating or 0,
                reverse=True,
            )
        elif sort_order == SortOrder.RELEVANCE:
            # Relevance: interleave results from different marketplaces
            return self._interleave_results(products)
        else:
            # Unknown: maintain current order
            return products

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

        # Sort by total cost (including taxes if available)
        sorted_by_price = sorted(products, key=self._get_comparable_price)

        # Assign price ranks
        for rank, product in enumerate(sorted_by_price, start=1):
            product.price_rank = rank

        # Mark the cheapest as best price
        # sorted_by_price is guaranteed non-empty because we check products above
        sorted_by_price[0].is_best_price = True

    def _get_comparable_price(self, product: EnrichedProduct) -> Decimal:
        """Get the price to use for comparison (total with taxes if available)."""
        if product.tax_info:
            return product.tax_info.total_with_taxes
        return product.product.total_price

    def _calculate_taxes(
        self,
        products: list[EnrichedProduct],
        destination_country: str,
    ) -> None:
        """Calculate import taxes for all products."""
        for product in products:
            tax_info = self._calculate_product_tax(product.product, destination_country)
            if tax_info:
                product.tax_info = tax_info

    def _calculate_product_tax(
        self,
        product: ProductResult,
        destination_country: str,
    ) -> TaxInfo | None:
        """Calculate tax for a single product."""
        request = TaxCalculationRequest(
            product_price=product.price,
            shipping_cost=product.shipping_cost or Decimal("0"),
            source_currency=product.currency,
            destination_country=destination_country,
        )

        result = self._tax_calculator.calculate(request)

        if isinstance(result, Success):
            breakdown: TaxBreakdown = result.value
            return TaxInfo(
                product_price_usd=breakdown.product_price_usd,
                shipping_cost_usd=breakdown.shipping_cost_usd,
                customs_duty=breakdown.customs_duty,
                vat=breakdown.vat,
                total_taxes=breakdown.total_taxes,
                total_with_taxes=breakdown.total_cost,
                destination_country=breakdown.destination_country,
                destination_country_name=breakdown.destination_country_name,
                de_minimis_applied=breakdown.de_minimis_applied,
                is_estimated=breakdown.is_estimated,
                notes=breakdown.notes,
            )

        logger.warning(
            "Failed to calculate taxes for product",
            product_id=product.id,
            error=str(result.error),
        )
        return None

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
