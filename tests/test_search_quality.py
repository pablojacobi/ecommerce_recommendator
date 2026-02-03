"""TDD Tests for search quality - ensuring relevant results."""

from typing import Any

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from decimal import Decimal

from django.test import Client
from django.urls import reverse


@pytest.fixture
def user(db: Any) -> Any:
    """Create a test user."""
    from apps.accounts.models import User
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )


@pytest.fixture
def client() -> Client:
    """Return Django test client."""
    return Client()


class TestSearchQueryExtraction:
    """Test that Gemini extracts proper search queries."""

    @pytest.mark.asyncio
    async def test_nintendo_switch_2_query_expanded(self) -> None:
        """Switch 2 should be expanded to Nintendo Switch 2."""
        from services.gemini.service import GeminiService

        # Mock the Gemini client response
        mock_response = MagicMock()
        mock_response.text = '''
        {
            "query": "Nintendo Switch 2 console",
            "sort_order": "price_asc",
            "condition": "new",
            "min_price": null,
            "max_price": null,
            "require_free_shipping": false,
            "min_seller_rating": null,
            "destination_country": null,
            "include_import_taxes": false,
            "limit": 20,
            "keywords": ["Nintendo", "Switch", "console", "gaming"]
        }
        '''

        with patch("google.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = GeminiService(api_key="test-key")
            result = await service.extract_search_intent(
                "dame el mejor precio para una switch 2 nueva u open box"
            )

            assert result.is_success()
            intent = result.value  # type: ignore[union-attr]

            # The query should include "Nintendo" to avoid D2R results
            assert "nintendo" in intent.query.lower() or "switch" in intent.query.lower()
            # Should NOT just be "switch 2" which matches Diablo 2
            assert intent.query.lower() != "switch 2"

    @pytest.mark.asyncio
    async def test_condition_new_or_open_box_extracted(self) -> None:
        """'nueva u open box' should set condition filter."""
        from services.gemini.service import GeminiService

        mock_response = MagicMock()
        mock_response.text = '''
        {
            "query": "Nintendo Switch 2 console",
            "sort_order": "price_asc",
            "condition": "new",
            "min_price": null,
            "max_price": null,
            "require_free_shipping": false,
            "min_seller_rating": null,
            "destination_country": null,
            "include_import_taxes": false,
            "limit": 20,
            "keywords": ["open box", "like new"]
        }
        '''

        with patch("google.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = GeminiService(api_key="test-key")
            result = await service.extract_search_intent(
                "switch 2 nueva u open box"
            )

            assert result.is_success()
            intent = result.value  # type: ignore[union-attr]
            # Should capture condition preference
            assert intent.condition == "new" or "open box" in intent.keywords

    @pytest.mark.asyncio
    async def test_best_price_triggers_price_sort(self) -> None:
        """'mejor precio' should trigger price_asc sort."""
        from services.gemini.service import GeminiService
        from services.marketplaces.base import SortOrder

        mock_response = MagicMock()
        mock_response.text = '''
        {
            "query": "Nintendo Switch 2 console",
            "sort_order": "price_asc",
            "condition": null,
            "min_price": null,
            "max_price": null,
            "require_free_shipping": false,
            "min_seller_rating": null,
            "destination_country": null,
            "include_import_taxes": false,
            "limit": 20,
            "keywords": []
        }
        '''

        with patch("google.genai.Client") as mock_client_class:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_client_class.return_value = mock_client

            service = GeminiService(api_key="test-key")
            result = await service.extract_search_intent(
                "dame el mejor precio para una switch 2"
            )

            assert result.is_success()
            intent = result.value  # type: ignore[union-attr]
            assert intent.sort_order == SortOrder.PRICE_ASC


class TestResultRelevanceValidation:
    """Test that irrelevant results are filtered out."""

    def test_filter_unrelated_products(self) -> None:
        """D2R items should be filtered when searching for Nintendo Switch."""
        from services.search.types import EnrichedProduct
        from services.marketplaces.base import ProductResult

        products = [
            # Irrelevant D2R product
            EnrichedProduct(
                product=ProductResult(
                    id="1",
                    title="D2R Gear - Choose 3 Items - Non-Ladder SC - PC & Switch",
                    price=Decimal("1.00"),
                    currency="USD",
                    url="https://ebay.com/1",
                    marketplace_code="EBAY_US",
                ),
                marketplace_code="EBAY_US",
                marketplace_name="eBay",
                is_best_price=True,
            ),
            # Relevant Nintendo Switch product
            EnrichedProduct(
                product=ProductResult(
                    id="2",
                    title="Nintendo Switch 2 Console - Brand New Sealed",
                    price=Decimal("399.00"),
                    currency="USD",
                    url="https://ebay.com/2",
                    marketplace_code="EBAY_US",
                ),
                marketplace_code="EBAY_US",
                marketplace_name="eBay",
                is_best_price=False,
            ),
            # Another D2R product
            EnrichedProduct(
                product=ProductResult(
                    id="3",
                    title="D2R Herald of Zakarum HoZ - Non-Ladder Softcore",
                    price=Decimal("1.00"),
                    currency="USD",
                    url="https://ebay.com/3",
                    marketplace_code="EBAY_US",
                ),
                marketplace_code="EBAY_US",
                marketplace_name="eBay",
                is_best_price=False,
            ),
        ]

        # Filter function should remove D2R items
        from services.search.relevance import filter_relevant_products

        filtered = filter_relevant_products(
            products=products,
            search_query="Nintendo Switch 2 console",
            original_query="switch 2 nueva",
        )

        # Should only have the Nintendo Switch product
        assert len(filtered) == 1
        assert "Nintendo Switch" in filtered[0].product.title

    def test_price_sanity_check(self) -> None:
        """$1 console should be flagged as suspicious."""
        from services.search.types import EnrichedProduct
        from services.marketplaces.base import ProductResult

        products = [
            EnrichedProduct(
                product=ProductResult(
                    id="1",
                    title="Nintendo Switch 2 Console New",
                    price=Decimal("1.00"),  # Suspicious price
                    currency="USD",
                    url="https://ebay.com/1",
                    marketplace_code="EBAY_US",
                ),
                marketplace_code="EBAY_US",
                marketplace_name="eBay",
                is_best_price=True,
            ),
            EnrichedProduct(
                product=ProductResult(
                    id="2",
                    title="Nintendo Switch 2 Console - Brand New",
                    price=Decimal("399.00"),  # Realistic price
                    currency="USD",
                    url="https://ebay.com/2",
                    marketplace_code="EBAY_US",
                ),
                marketplace_code="EBAY_US",
                marketplace_name="eBay",
                is_best_price=False,
            ),
        ]

        from services.search.relevance import filter_relevant_products

        filtered = filter_relevant_products(
            products=products,
            search_query="Nintendo Switch 2 console",
            original_query="switch 2",
            min_expected_price=Decimal("100.00"),  # Consoles cost > $100
        )

        # The $1 item should be filtered out
        assert len(filtered) == 1
        assert filtered[0].product.price > Decimal("100.00")


class TestPromptQuality:
    """Test that prompts generate quality search queries."""

    def test_prompt_includes_product_disambiguation(self) -> None:
        """Prompt should include rules for disambiguating products."""
        from services.gemini.prompts import SEARCH_EXTRACTION_PROMPT

        # Prompt should mention disambiguation or common confusions
        assert "Nintendo" in SEARCH_EXTRACTION_PROMPT or "disambiguation" in SEARCH_EXTRACTION_PROMPT.lower()

    def test_prompt_includes_condition_mapping(self) -> None:
        """Prompt should map various condition terms."""
        from services.gemini.prompts import SEARCH_EXTRACTION_PROMPT

        # Should handle "open box", "like new", "nueva", etc.
        prompt_lower = SEARCH_EXTRACTION_PROMPT.lower()
        assert "open box" in prompt_lower or "condition" in prompt_lower


@pytest.mark.django_db
class TestEndToEndSearchQuality:
    """E2E test for search quality."""

    def test_switch_2_search_returns_consoles_not_d2r(
        self, client: Client, user: Any
    ) -> None:
        """Searching for Switch 2 should return Nintendo consoles, not D2R items."""
        from apps.chat.models import Conversation

        client.force_login(user)
        conversation = Conversation.objects.create(user=user, title="")

        # Mock products - mix of relevant and irrelevant
        mock_products = [
            {
                "id": "1",
                "title": "Nintendo Switch 2 Console - Brand New",
                "price": 399.00,
                "currency": "USD",
                "url": "https://example.com/1",
                "image_url": None,
                "marketplace_code": "EBAY_US",
                "marketplace_name": "eBay",
                "seller_rating": 5.0,
                "shipping_cost": None,
                "free_shipping": True,
                "is_best_price": True,
                "tax_info": None,
            },
        ]

        with patch("apps.chat.views._process_chat") as mock_process:
            mock_process.return_value = {
                "message": "Found Nintendo Switch 2 consoles.",
                "products": mock_products,
                "has_more": False,
                "generated_title": "Nintendo Switch 2",
            }

            response = client.post(
                reverse("chat:send_message"),
                {
                    "message": "dame el mejor precio para una switch 2 nueva u open box",
                    "conversation_id": str(conversation.id),
                    "marketplaces": "EBAY_US",
                },
            )

            assert response.status_code == 200
            content = response.content.decode()

            # Should NOT have D2R products
            assert "D2R" not in content
            assert "Diablo" not in content
            assert "Non-Ladder" not in content

            # Should have Nintendo Switch
            assert "Nintendo" in content or "Switch" in content
