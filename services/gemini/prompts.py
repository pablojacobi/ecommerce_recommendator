"""Prompt templates for Gemini AI service."""

SYSTEM_PROMPT = """You are a shopping assistant that helps users find products.
You work with marketplaces like MercadoLibre and eBay.

Your task is to analyze user queries and extract structured search parameters.

Available sort orders:
- relevance: Best match (default)
- price_asc: Lowest price first
- price_desc: Highest price first
- newest: Most recently listed
- best_seller: Best selling items

Available conditions:
- new: Brand new items
- used: Pre-owned items
- refurbished: Certified refurbished

When analyzing a query, extract:
1. The main search query (what product they're looking for)
2. Sort preference (if mentioned: cheapest, best, newest, etc.)
3. Price range (if mentioned)
4. Shipping preferences (free shipping, shipping to specific country)
5. Seller quality preferences (good reputation, high ratings)
6. Condition preferences (new, used, refurbished)
7. Quantity of results desired (if mentioned)

Always respond with valid JSON only. No additional text or explanation."""

SEARCH_EXTRACTION_PROMPT = """Analyze this shopping query and extract search parameters.

User query: "{query}"

Respond with a JSON object containing these fields:
{{
    "query": "the main search terms to find the product",
    "sort_order": "relevance" | "price_asc" | "price_desc" | "newest" | null,
    "min_price": number or null,
    "max_price": number or null,
    "require_free_shipping": boolean,
    "min_seller_rating": number (0-5) or null,
    "condition": "new" | "used" | "refurbished" | null,
    "destination_country": "two-letter country code" or null,
    "include_import_taxes": boolean,
    "limit": number (default 20, max 100),
    "keywords": ["additional", "filter", "keywords"]
}}

Examples:

Query: "laptop gaming barata con envío gratis"
Response:
{{
    "query": "laptop gaming",
    "sort_order": "price_asc",
    "min_price": null,
    "max_price": null,
    "require_free_shipping": true,
    "min_seller_rating": null,
    "condition": null,
    "destination_country": null,
    "include_import_taxes": false,
    "limit": 20,
    "keywords": ["gaming"]
}}

Query: "iPhone 15 Pro Max nuevo de vendedores con buena reputación"
Response:
{{
    "query": "iPhone 15 Pro Max",
    "sort_order": "relevance",
    "min_price": null,
    "max_price": null,
    "require_free_shipping": false,
    "min_seller_rating": 4.0,
    "condition": "new",
    "destination_country": null,
    "include_import_taxes": false,
    "limit": 20,
    "keywords": []
}}

Query: "aspiradora 1600W la más barata con envío a Chile incluyendo impuestos"
Response:
{{
    "query": "aspiradora 1600W",
    "sort_order": "price_asc",
    "min_price": null,
    "max_price": null,
    "require_free_shipping": false,
    "min_seller_rating": null,
    "condition": null,
    "destination_country": "CL",
    "include_import_taxes": true,
    "limit": 20,
    "keywords": ["1600W"]
}}

Now analyze: "{query}"
Respond with JSON only:"""

REFINEMENT_PROMPT = """Analyze this refinement request in context of previous search.

Previous search: "{previous_query}"
Previous results count: {results_count}

User request: "{refinement_query}"

Determine the type of refinement and extract parameters.

Refinement types:
- "filter": Add filters to narrow down results
- "sort": Change how results are sorted
- "compare": Compare products on specific criteria
- "best_value": Find best price/quality ratio
- "cheapest": Get the cheapest from current results
- "more": Request more results

Respond with a JSON object:
{{
    "refinement_type": "filter" | "sort" | "compare" | "best_value" | "cheapest",
    "filter_criteria": {{"key": "value"}} or {{}},
    "sort_preference": "sort_order" or null,
    "comparison_criteria": "what to compare" or null,
    "requires_new_search": boolean
}}

Examples:

Request: "de esos dame los más baratos"
Response:
{{
    "refinement_type": "cheapest",
    "filter_criteria": {{}},
    "sort_preference": "price_asc",
    "comparison_criteria": null,
    "requires_new_search": false
}}

Request: "recomiéndame el de mejor relación precio/calidad"
Response:
{{
    "refinement_type": "best_value",
    "filter_criteria": {{}},
    "sort_preference": null,
    "comparison_criteria": "price_quality_ratio",
    "requires_new_search": false
}}

Request: "solo los nuevos con envío gratis"
Response:
{{
    "refinement_type": "filter",
    "filter_criteria": {{"condition": "new", "free_shipping": "true"}},
    "sort_preference": null,
    "comparison_criteria": null,
    "requires_new_search": false
}}

Now analyze: "{refinement_query}"
Respond with JSON only:"""

INTENT_CLASSIFICATION_PROMPT = """Classify this user message in a shopping conversation.

Previous context: {context_summary}
User message: "{message}"

Classify as one of:
- "search": A new product search request
- "refinement": Modifying or filtering previous results
- "more_results": Requesting additional results
- "clarification": Asking for details about a product
- "comparison": Comparing products

Respond with JSON:
{{
    "intent_type": "search" | "refinement" | "more_results" | "clarification",
    "confidence": 0.0 to 1.0
}}"""
