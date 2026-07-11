"""Extra branch-coverage tests for the eBay client and search orchestrator.

Covers two otherwise-unreached branches:

* ``services/marketplaces/ebay/client.py`` -- the ``category_ids`` query
  parameter that is only added when ``category_id`` is provided.
* ``services/search/orchestrator.py`` -- the fallback ``else`` branch of
  ``_apply_single_sort`` that returns products unchanged for an unknown
  (or ``None``) sort order.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.result import Success
from services.marketplaces.base import ProductResult
from services.marketplaces.ebay.client import EbayClient
from services.search.orchestrator import SearchOrchestrator
from services.search.types import EnrichedProduct


class TestEbaySearchCategoryFilter:
    """Cover the category_ids query parameter branch in EbayClient.search."""

    @pytest.mark.asyncio
    async def test_search_includes_category_ids_when_provided(self) -> None:
        """A provided category_id is sent as the category_ids parameter."""
        client = EbayClient(app_id="test-app-id", cert_id="test-cert-id")
        client._access_token = "test-token"
        client._token_expires_at = datetime.now(UTC) + timedelta(hours=1)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"itemSummaries": [], "total": 0}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_response
            mock_get_client.return_value = mock_http

            result = await client.search(query="laptop", category_id="9355")

        assert isinstance(result, Success)
        params = mock_http.request.call_args.kwargs["params"]
        assert params["category_ids"] == "9355"


class TestOrchestratorUnknownSortOrder:
    """Cover the fallback branch of _apply_single_sort for unknown sort order."""

    def test_apply_single_sort_none_returns_products_unchanged(self) -> None:
        """An unrecognized (None) sort order leaves the products unchanged."""
        orchestrator = SearchOrchestrator(MagicMock())
        products = [
            EnrichedProduct(
                product=ProductResult(
                    id="1",
                    marketplace_code="MLC",
                    title="Laptop",
                    price=Decimal("100"),
                    currency="CLP",
                    url="https://mlc.com/1",
                ),
                marketplace_code="MLC",
                marketplace_name="MercadoLibre Chile",
            ),
        ]

        result = orchestrator._apply_single_sort(products, None)

        assert result == products
        assert len(result) == 1
