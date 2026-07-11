"""Tests for search relevance filtering (services/search/relevance.py)."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from services.marketplaces.base import ProductResult
from services.search.relevance import (
    _calculate_relevance_score,
    _detect_category,
    _extract_key_terms,
    _filter_with_ai,
    filter_relevant_products,
    filter_relevant_products_async,
    is_likely_physical_product,
)
from services.search.types import EnrichedProduct


def make_enriched(title: str, price: str, product_id: str = "1") -> EnrichedProduct:
    """Build an EnrichedProduct wrapping a ProductResult."""
    return EnrichedProduct(
        product=ProductResult(
            id=product_id,
            marketplace_code="EBAY_US",
            title=title,
            price=Decimal(price),
            currency="USD",
            url=f"https://ebay.com/{product_id}",
        ),
        marketplace_code="EBAY_US",
        marketplace_name="eBay",
    )


def make_gemini_client(text: str) -> MagicMock:
    """Build a mock Gemini client whose model returns the given text."""
    response = MagicMock()
    response.text = text
    client = MagicMock()
    client.models.generate_content.return_value = response
    return client


class TestFilterRelevantProductsAsync:
    """Tests for the filter_relevant_products_async entry point."""

    async def test_empty_products_returned_as_is(self) -> None:
        """An empty product list short-circuits and is returned unchanged."""
        result = await filter_relevant_products_async([], "switch", "switch 2")

        assert result == []

    async def test_no_client_uses_basic_filter(self) -> None:
        """Without a Gemini client, basic heuristic filtering is used."""
        products = [make_enriched("Nintendo Switch 2 Console New", "399")]

        result = await filter_relevant_products_async(
            products,
            "Nintendo Switch 2 console",
            "switch 2",
        )

        assert len(result) == 1
        assert "Nintendo" in result[0].product.title

    async def test_with_client_uses_ai_filter(self) -> None:
        """A Gemini client routes filtering through the AI classifier."""
        products = [make_enriched("Nintendo Switch Console", "399")]
        client = make_gemini_client('[{"id":"1","physical":true,"matches":true}]')

        result = await filter_relevant_products_async(
            products,
            "switch",
            "switch 2",
            gemini_client=client,
        )

        assert len(result) == 1
        assert client.models.generate_content.called

    async def test_ai_exception_falls_back_to_basic(self) -> None:
        """When the AI classifier raises, basic filtering is used instead."""
        products = [make_enriched("Nintendo Switch 2 Console New", "399")]
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("boom")

        result = await filter_relevant_products_async(
            products,
            "Nintendo Switch 2 console",
            "switch 2",
            gemini_client=client,
        )

        assert len(result) == 1
        assert "Nintendo" in result[0].product.title


class TestFilterWithAI:
    """Tests for the _filter_with_ai classifier."""

    async def test_empty_response_returns_products(self) -> None:
        """An empty AI response returns the products unchanged."""
        products = [make_enriched("Nintendo Switch", "399")]
        client = make_gemini_client("")

        result = await _filter_with_ai(products, client, "switch", "switch 2")

        assert result == products

    async def test_invalid_json_returns_products(self) -> None:
        """Unparseable AI output returns the products unchanged."""
        products = [make_enriched("Nintendo Switch", "399")]
        client = make_gemini_client("not valid json")

        # Empty original_query exercises the search_query fallback.
        result = await _filter_with_ai(products, client, "switch", "")

        assert result == products

    async def test_strips_json_code_fence(self) -> None:
        """A ```json fenced response is parsed correctly."""
        products = [make_enriched("Nintendo Switch", "399")]
        client = make_gemini_client('```json\n[{"id":"1","physical":true,"matches":true}]\n```')

        result = await _filter_with_ai(products, client, "switch", "switch 2")

        assert len(result) == 1

    async def test_strips_plain_code_fence(self) -> None:
        """A plain ``` fenced response is parsed correctly."""
        products = [make_enriched("Nintendo Switch", "399")]
        client = make_gemini_client('```\n[{"id":"1","physical":true,"matches":true}]\n```')

        result = await _filter_with_ai(products, client, "switch", "switch 2")

        assert len(result) == 1

    async def test_valid_classifications_kept(self) -> None:
        """Products flagged physical and matching are kept (default matches=True)."""
        products = [
            make_enriched("Nintendo Switch", "399", "1"),
            make_enriched("PS5 Console", "499", "2"),
        ]
        # First item omits "matches" to exercise the backwards-compat default.
        client = make_gemini_client(
            '[{"id":"1","physical":true},{"id":"2","physical":true,"matches":true}]'
        )

        result = await _filter_with_ai(products, client, "console", "console")

        assert len(result) == 2

    async def test_relaxes_to_physical_only(self) -> None:
        """Few matches but more physical items relaxes to physical-only filter."""
        products = [
            make_enriched("Nintendo Switch", "399", "1"),
            make_enriched("Switch Case", "10", "2"),
            make_enriched("Switch Digital Code", "5", "3"),
        ]
        client = make_gemini_client(
            "["
            '{"id":"1","physical":true,"matches":true},'
            '{"id":"2","physical":true,"matches":false},'
            '{"id":"3","physical":false,"matches":false},'
            '{"id":"9","physical":true,"matches":true}'  # out-of-range id, ignored
            "]"
        )

        result = await _filter_with_ai(products, client, "switch", "switch 2")

        titles = [p.product.title for p in result]
        assert titles == ["Nintendo Switch", "Switch Case"]

    async def test_all_filtered_returns_top_five(self) -> None:
        """When nothing survives filtering, the top products are returned."""
        products = [
            make_enriched("Digital Code", "5", "1"),
            make_enriched("Game Trade", "3", "2"),
        ]
        client = make_gemini_client(
            "["
            '{"id":"1","physical":false,"matches":false},'
            '{"id":"2","physical":false,"matches":false}'
            "]"
        )

        result = await _filter_with_ai(products, client, "switch", "switch 2")

        assert result == products


class TestFilterRelevantProductsSync:
    """Tests for the synchronous basic filter."""

    def test_empty_products_returned_as_is(self) -> None:
        """An empty product list is returned unchanged."""
        assert filter_relevant_products([], "switch", "switch 2") == []

    def test_category_min_price_default(self) -> None:
        """Without an explicit threshold, the category default is used."""
        products = [make_enriched("Nintendo Switch 2 Console New", "399")]

        result = filter_relevant_products(products, "Nintendo Switch 2 console", "switch 2")

        assert len(result) == 1

    def test_explicit_min_price_filters_suspicious(self) -> None:
        """An explicit min price drops suspiciously cheap items."""
        products = [
            make_enriched("Nintendo Switch 2 Console New", "1", "1"),
            make_enriched("Nintendo Switch 2 Console Brand New", "399", "2"),
        ]

        result = filter_relevant_products(
            products,
            "Nintendo Switch 2 console",
            "switch 2",
            min_expected_price=Decimal("100.00"),
        )

        assert len(result) == 1
        assert result[0].product.price > Decimal("100.00")

    def test_keeps_relevant_drops_irrelevant(self) -> None:
        """Relevant products are kept and irrelevant ones dropped."""
        products = [
            make_enriched("Nintendo Switch 2 Console New", "399", "1"),
            make_enriched("D2R Gear Choose 3 Items Non-Ladder", "1", "2"),
        ]

        result = filter_relevant_products(products, "Nintendo Switch 2 console", "switch 2")

        assert len(result) == 1
        assert "Nintendo" in result[0].product.title

    def test_all_dropped_returns_top_five(self) -> None:
        """When everything scores too low, the top products are returned."""
        products = [make_enriched("Random Junk Item", "1")]

        result = filter_relevant_products(products, "iphone 15 pro", "iphone 15 pro")

        assert result == products


class TestDetectCategory:
    """Tests for _detect_category."""

    def test_console(self) -> None:
        assert _detect_category("nintendo switch", "") == "console"

    def test_phone(self) -> None:
        assert _detect_category("iphone 15", "") == "phone"

    def test_laptop(self) -> None:
        assert _detect_category("dell laptop", "") == "laptop"

    def test_general_fallback(self) -> None:
        assert _detect_category("random gadget", "") == "general"


class TestExtractKeyTerms:
    """Tests for _extract_key_terms."""

    def test_filters_stopwords_and_short_words(self) -> None:
        """Stop words and words of length <= 2 are excluded."""
        terms = _extract_key_terms("el mejor iphone 15 pro", "")

        assert "iphone" in terms
        assert "pro" in terms
        assert "el" not in terms  # stop word
        assert "mejor" not in terms  # stop word
        assert "15" not in terms  # too short


class TestCalculateRelevanceScore:
    """Tests for _calculate_relevance_score branch behaviour."""

    def test_price_far_below_min(self) -> None:
        """Price ratio below 0.05 applies the largest penalty."""
        product = make_enriched("Nintendo Switch Console", "1")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"nintendo", "switch"},
            category="general",
            min_expected_price=Decimal("100"),
        )

        assert score == pytest.approx(0.4)

    def test_price_moderately_below_min(self) -> None:
        """Price ratio between 0.05 and 0.15 applies a medium penalty."""
        product = make_enriched("Nintendo Switch Console", "10")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"nintendo", "switch"},
            category="general",
            min_expected_price=Decimal("100"),
        )

        assert score == pytest.approx(0.7)

    def test_price_slightly_below_min_no_penalty(self) -> None:
        """Price ratio at or above 0.15 applies no price penalty."""
        product = make_enriched("Nintendo Switch Console", "50")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"nintendo", "switch"},
            category="general",
            min_expected_price=Decimal("100"),
        )

        assert score == pytest.approx(1.0)

    def test_price_above_min_no_penalty(self) -> None:
        """A price above the minimum skips the price check entirely."""
        product = make_enriched("Nintendo Switch Console", "200")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"nintendo", "switch"},
            category="general",
            min_expected_price=Decimal("100"),
        )

        assert score == pytest.approx(1.0)

    def test_low_term_overlap(self) -> None:
        """Overlap below 0.2 applies the largest overlap penalty."""
        product = make_enriched("Random Gadget Item", "500")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"apple", "macbook", "pro", "m3", "laptop"},
            category="general",
            min_expected_price=Decimal("100"),
        )

        assert score == pytest.approx(0.6)

    def test_medium_term_overlap(self) -> None:
        """Overlap between 0.2 and 0.4 applies a medium overlap penalty."""
        product = make_enriched("Switch Thing Extra", "500")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"one", "two", "three", "four", "switch"},
            category="general",
            min_expected_price=Decimal("100"),
        )

        assert score == pytest.approx(0.8)

    def test_console_with_brand(self) -> None:
        """A console with a known brand gets no category penalty."""
        product = make_enriched("Nintendo Switch Console", "399")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"nintendo", "switch"},
            category="console",
            min_expected_price=Decimal("80"),
        )

        assert score == pytest.approx(1.0)

    def test_console_without_brand(self) -> None:
        """A console without a known brand gets a category penalty."""
        product = make_enriched("Generic Handheld Player", "399")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"generic", "handheld", "player"},
            category="console",
            min_expected_price=Decimal("80"),
        )

        assert score == pytest.approx(0.7)

    def test_phone_with_brand(self) -> None:
        """A phone with a known brand gets no category penalty."""
        product = make_enriched("Apple iPhone Pro", "999")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"apple", "iphone", "pro"},
            category="phone",
            min_expected_price=Decimal("40"),
        )

        assert score == pytest.approx(1.0)

    def test_phone_without_brand(self) -> None:
        """A phone without a known brand gets a category penalty."""
        product = make_enriched("Generic Smart Device", "999")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"generic", "smart", "device"},
            category="phone",
            min_expected_price=Decimal("40"),
        )

        assert score == pytest.approx(0.8)

    def test_laptop_with_word(self) -> None:
        """A laptop with a known keyword gets no category penalty."""
        product = make_enriched("Dell Laptop Computer", "999")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"dell", "laptop", "computer"},
            category="laptop",
            min_expected_price=Decimal("150"),
        )

        assert score == pytest.approx(1.0)

    def test_laptop_without_word(self) -> None:
        """A laptop without a known keyword gets a category penalty."""
        product = make_enriched("Dell Ultra Computer", "999")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"dell", "ultra", "computer"},
            category="laptop",
            min_expected_price=Decimal("150"),
        )

        assert score == pytest.approx(0.7)

    def test_uncategorized_skips_category_checks(self) -> None:
        """A category with no specific checks skips straight to the score."""
        product = make_enriched("Some Cool Product", "999")

        score = _calculate_relevance_score(
            product=product,
            query_terms={"some", "cool", "product"},
            category="tv",
            min_expected_price=Decimal("80"),
        )

        assert score == pytest.approx(1.0)


class TestIsLikelyPhysicalProduct:
    """Tests for is_likely_physical_product."""

    def test_cheap_virtual_item_is_not_physical(self) -> None:
        """A cheap item with virtual hints is flagged as not physical."""
        product = make_enriched("Steam Digital Code", "5")

        assert is_likely_physical_product(product) is False

    def test_cheap_tangible_item_is_physical(self) -> None:
        """A cheap item without virtual hints is treated as physical."""
        product = make_enriched("USB Cable Adapter", "5")

        assert is_likely_physical_product(product) is True

    def test_expensive_item_is_physical(self) -> None:
        """An item priced at or above the threshold is treated as physical."""
        product = make_enriched("Gaming Laptop", "500")

        assert is_likely_physical_product(product) is True
