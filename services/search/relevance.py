"""Relevance filtering for search results using AI classification."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import TYPE_CHECKING

from core.logging import get_logger

if TYPE_CHECKING:
    from services.search.types import EnrichedProduct

logger = get_logger(__name__)

# Minimum expected prices by category (USD) - used as a signal, not hard filter
CATEGORY_MIN_PRICES = {
    "console": Decimal("80.00"),
    "laptop": Decimal("150.00"),
    "phone": Decimal("40.00"),
    "tablet": Decimal("80.00"),
    "tv": Decimal("80.00"),
    "camera": Decimal("30.00"),
    "headphones": Decimal("5.00"),
    "watch": Decimal("15.00"),
    "gaming": Decimal("10.00"),
    "general": Decimal("1.00"),
}

# Prompt for AI classification and relevance
CLASSIFICATION_PROMPT = """Classify each product as PHYSICAL or VIRTUAL, and check if it MATCHES the search query.

PHYSICAL = tangible items that ship (consoles, phones, laptops, cables, cases, accessories)
VIRTUAL = digital goods, subscriptions, in-game items, codes, memberships, game currency, game trades, DLC

MATCH RULES:
- Match the EXACT product model/version requested in the query
- If query specifies a version number (e.g., "2", "6+", "15"), only match that exact version
- For technical products, use your knowledge of model codes to verify compatibility
- Older/different versions of the same product line should NOT match

Search query: "{query}"

Products:
{products}

Output JSON array: [{{"id":"1","physical":true,"matches":true}},{{"id":"2","physical":false,"matches":false}}...]
JSON only:"""


async def filter_relevant_products_async(
    products: list[EnrichedProduct],
    search_query: str,
    original_query: str,
    gemini_client=None,
) -> list[EnrichedProduct]:
    """
    Filter products using AI classification.

    Args:
        products: List of products to filter.
        search_query: The expanded search query used.
        original_query: The user's original query.
        gemini_client: Optional Gemini client for AI classification.

    Returns:
        Filtered list of relevant products.
    """
    if not products:
        return products

    if gemini_client is None:
        # Fall back to basic filtering if no AI client
        return _filter_basic(products, search_query, original_query)

    try:
        return await _filter_with_ai(products, gemini_client, search_query, original_query)
    except Exception as e:
        logger.warning("AI classification failed, using basic filter", error=str(e))
        return _filter_basic(products, search_query, original_query)


async def _filter_with_ai(
    products: list[EnrichedProduct],
    gemini_client,
    search_query: str,
    original_query: str,
) -> list[EnrichedProduct]:
    """Filter products using Gemini AI classification and relevance check."""
    # Build product list for classification
    product_lines = []
    for i, p in enumerate(products):
        title = p.product.title[:80]  # Truncate for efficiency
        price = p.product.price
        product_lines.append(f'{i+1}. ${price} - {title}')

    # Use original query for better context on what user wants
    query_for_matching = original_query or search_query
    prompt = CLASSIFICATION_PROMPT.format(
        query=query_for_matching,
        products='\n'.join(product_lines)
    )

    # Call Gemini
    response = gemini_client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt,
        config={'temperature': 0.1},
    )

    if not response.text:
        logger.warning("Empty AI classification response")
        return products

    # Parse response
    text = response.text.strip()
    if text.startswith('```json'):
        text = text[7:]
    if text.startswith('```'):
        text = text[3:]
    if text.endswith('```'):
        text = text[:-3]
    text = text.strip()

    try:
        classifications = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse AI classification", error=str(e))
        return products

    # Build set of valid product IDs (physical AND matches query)
    valid_ids = set()
    physical_count = 0
    match_count = 0

    for item in classifications:
        idx = int(item.get('id', 0)) - 1
        if 0 <= idx < len(products):
            is_physical = item.get('physical', False)
            is_match = item.get('matches', True)  # Default to True for backwards compat

            if is_physical:
                physical_count += 1
            if is_match:
                match_count += 1

            # Must be both physical AND match the query
            if is_physical and is_match:
                valid_ids.add(idx)

    # Filter to only valid products
    filtered = [p for i, p in enumerate(products) if i in valid_ids]

    logger.info(
        "AI filtered products",
        original=len(products),
        physical=physical_count,
        matches_query=match_count,
        valid=len(filtered),
    )

    # If too few results, relax to just physical products
    if len(filtered) < 5 and physical_count > len(filtered):
        logger.warning(
            "Few matches, relaxing to physical-only filter",
            matches=len(filtered),
            physical=physical_count,
        )
        physical_ids = {
            int(item.get('id', 0)) - 1
            for item in classifications
            if item.get('physical', False)
        }
        filtered = [p for i, p in enumerate(products) if i in physical_ids]

    return filtered if filtered else products[:5]  # Fallback if all filtered


def filter_relevant_products(
    products: list[EnrichedProduct],
    search_query: str,
    original_query: str,
    min_expected_price: Decimal | None = None,
) -> list[EnrichedProduct]:
    """
    Filter products using basic rules (synchronous fallback).

    This is used when AI classification is not available.
    """
    return _filter_basic(products, search_query, original_query, min_expected_price)


def _filter_basic(
    products: list[EnrichedProduct],
    search_query: str,
    original_query: str,
    min_expected_price: Decimal | None = None,
) -> list[EnrichedProduct]:
    """Basic filtering using simple heuristics."""
    if not products:
        return products

    # Detect product category from query
    category = _detect_category(search_query, original_query)

    # Get minimum price threshold
    if min_expected_price is None:
        min_expected_price = CATEGORY_MIN_PRICES.get(category, Decimal("1.00"))

    # Extract key terms from queries
    query_terms = _extract_key_terms(search_query, original_query)

    filtered = []
    for product in products:
        score = _calculate_relevance_score(
            product=product,
            query_terms=query_terms,
            category=category,
            min_expected_price=min_expected_price,
        )

        if score >= 0.5:
            filtered.append(product)
        else:
            logger.debug(
                "Filtered out product",
                title=product.product.title[:50],
                score=score,
            )

    # If we filtered everything, return top results
    if not filtered and products:
        logger.warning(
            "All products filtered out, returning top 5",
            original_count=len(products),
        )
        return products[:5]

    return filtered


def _detect_category(search_query: str, original_query: str) -> str:
    """Detect the product category from the query."""
    combined = f"{search_query} {original_query}".lower()

    if any(term in combined for term in ["switch", "playstation", "xbox", "console", "ps5", "ps4"]):
        return "console"
    if any(term in combined for term in ["laptop", "notebook", "macbook"]):
        return "laptop"
    if any(term in combined for term in ["iphone", "samsung", "pixel", "phone", "celular", "móvil"]):
        return "phone"
    if any(term in combined for term in ["ipad", "tablet", "tab"]):
        return "tablet"
    if any(term in combined for term in ["tv", "television", "oled", "qled"]):
        return "tv"
    if any(term in combined for term in ["camera", "cámara", "dslr", "mirrorless"]):
        return "camera"
    if any(term in combined for term in ["headphone", "auricular", "airpod", "earbud"]):
        return "headphones"
    if any(term in combined for term in ["watch", "reloj", "smartwatch"]):
        return "watch"
    if any(term in combined for term in ["gaming", "gamer", "rtx", "gpu"]):
        return "gaming"

    return "general"


def _extract_key_terms(search_query: str, original_query: str) -> set[str]:
    """Extract key terms that should appear in relevant results."""
    combined = f"{search_query} {original_query}".lower()

    # Remove common words
    stop_words = {
        "the", "a", "an", "for", "to", "and", "or", "with", "in", "on",
        "el", "la", "los", "las", "un", "una", "para", "con", "de", "y", "o",
        "dame", "busco", "quiero", "mejor", "precio", "nueva", "nuevo", "new",
        "used", "usada", "usado", "open", "box",
    }

    words = re.findall(r'\b\w+\b', combined)
    terms = {w for w in words if w not in stop_words and len(w) > 2}

    return terms


def _calculate_relevance_score(
    product: EnrichedProduct,
    query_terms: set[str],
    category: str,
    min_expected_price: Decimal,
) -> float:
    """Calculate a simple relevance score for a product."""
    title = product.product.title
    title_lower = title.lower()
    price = product.product.price
    score = 1.0

    # Check price sanity for category
    if price < min_expected_price:
        price_ratio = float(price / min_expected_price)
        if price_ratio < 0.05:  # $5 for $100 item
            score -= 0.6
        elif price_ratio < 0.15:
            score -= 0.3

    # Check term overlap with query
    title_words = set(re.findall(r'\b\w+\b', title_lower))
    overlap = query_terms & title_words
    overlap_ratio = len(overlap) / max(len(query_terms), 1)

    if overlap_ratio < 0.2:
        score -= 0.4
    elif overlap_ratio < 0.4:
        score -= 0.2

    # Category-specific checks
    if category == "console":
        console_brands = ["nintendo", "switch", "playstation", "sony", "xbox", "microsoft", "ps5", "ps4"]
        if not any(brand in title_lower for brand in console_brands):
            score -= 0.3

    elif category == "phone":
        phone_brands = ["iphone", "samsung", "galaxy", "pixel", "oneplus", "xiaomi", "apple"]
        if not any(brand in title_lower for brand in phone_brands):
            score -= 0.2

    elif category == "laptop":
        laptop_words = ["laptop", "notebook", "macbook", "chromebook", "thinkpad"]
        if not any(w in title_lower for w in laptop_words):
            score -= 0.3

    return max(0.0, score)


def is_likely_physical_product(product: EnrichedProduct) -> bool:
    """Quick heuristic check if product is likely physical."""
    title_lower = product.product.title.lower()
    price = product.product.price

    # Very cheap items with certain keywords are likely virtual
    if price < Decimal("20.00"):
        virtual_hints = ["code", "key", "digital", "download", "membership",
                        "subscription", "shiny", "6iv", "trade", "v-bucks"]
        if any(hint in title_lower for hint in virtual_hints):
            return False

    return True
