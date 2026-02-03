"""Prompt templates for Gemini AI service."""

SYSTEM_PROMPT = """You are a JSON extraction API. You MUST respond with ONLY valid JSON, no explanations, no markdown, no text before or after the JSON.

When extracting search parameters:
- Expand product names: "switch" → "Nintendo Switch", "ps5" → "PlayStation 5"
- sort_criteria: array of sort orders, first = primary, second = secondary, etc.
  Options: "relevance", "price_asc", "price_desc", "newest", "best_seller"
- condition options: "new", "used", "refurbished"

RESPOND WITH JSON ONLY."""

SEARCH_EXTRACTION_PROMPT = """Extract search parameters from user query. Output ONLY JSON.

RULES:
1. Expand abbreviated product names to full brand names
2. Keep query SHORT (2-5 words max) for effective e-commerce search
3. Translate sorting preferences:
   - "mejor precio/cheapest/BBB/barato" → sort_criteria:["price_asc"]
   - "mejor reputación/best sellers/buen vendedor" → include "best_seller" in sort_criteria
4. Translate condition: "nueva/new" → condition:"new", "usada/used" → condition:"used"
5. sort_criteria is an ARRAY supporting multiple criteria
6. Select appropriate ebay_category_id based on product type
7. For performance requirements, translate to specific hardware model names:
   - Gaming at 4K/high settings requires dedicated GPU (include GPU series: RTX, GTX)
   - Video editing requires powerful CPU/GPU
   - Use model codes that appear in product listings

EBAY CATEGORY IDs:
- Video Game Consoles: 139971
- Laptops/Notebooks: 175672
- Cell Phones: 9355
- Tablets: 171485
- TVs: 11071
- Headphones: 112529
- Smartwatches: 178893
- Network Equipment: 11176

Output format:
{{"query":"<2-5 word search query>","sort_criteria":["<sort1>","<sort2>"],"condition":"<new|used|null>","ebay_category_id":"<id>","min_price":null,"max_price":null,"require_free_shipping":false,"limit":20,"keywords":[]}}

Input: "{query}"
Output:"""

REFINEMENT_PROMPT = """Analyze this refinement of previous search results. Output ONLY JSON.

Previous search: "{previous_query}"
Results: {results_count}

User says: "{refinement_query}"

Refinement types:
- "filter": Add filters (price, condition, shipping, seller rating)
- "sort": Change sort order (by price, rating, newest)
- "cheapest": Get cheapest results
- "best_rated": Get highest rated sellers
- "more": Show more results

filter_criteria options:
- "max_price": number
- "min_price": number
- "condition": "new" | "used" | "refurbished"
- "free_shipping": true
- "min_seller_rating": number (0-5, e.g., 4.5 for "good reputation")

sort_preference options: "price_asc", "price_desc", "rating_desc", "newest"

Examples:

"filtrar por vendedores con mejor reputación" →
{{"refinement_type":"best_rated","filter_criteria":{{"min_seller_rating":4.5}},"sort_preference":"rating_desc","requires_new_search":false}}

"solo los de menos de 500" →
{{"refinement_type":"filter","filter_criteria":{{"max_price":500}},"sort_preference":null,"requires_new_search":false}}

"los más baratos" →
{{"refinement_type":"cheapest","filter_criteria":{{}},"sort_preference":"price_asc","requires_new_search":false}}

"solo envío gratis" →
{{"refinement_type":"filter","filter_criteria":{{"free_shipping":true}},"sort_preference":null,"requires_new_search":false}}

"vendedores con buena reputación" →
{{"refinement_type":"best_rated","filter_criteria":{{"min_seller_rating":4.0}},"sort_preference":"rating_desc","requires_new_search":false}}

Input: "{refinement_query}"
Output:"""

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

TITLE_GENERATION_PROMPT = """Generate a short, descriptive title for a shopping conversation based on the user's first message.

User message: "{message}"

Rules:
1. Maximum 30 characters
2. Use the SAME LANGUAGE as the user's message
3. Focus on the product being searched
4. Be concise and descriptive
5. No quotes or special characters

Examples:
- "busco laptop gaming" → "Laptop gaming"
- "I need a cheap iPhone" → "iPhone search"
- "aspiradora potente" → "Aspiradora"
- "RTX 4070 graphics card" → "RTX 4070 GPU"

Respond with ONLY the title text, nothing else."""

RESPONSE_GENERATION_PROMPT = """Generate a friendly response for a shopping assistant based on search results.

CRITICAL: Respond in the SAME LANGUAGE as the user's query.
- Spanish query → Spanish response
- English query → English response

User query: "{query}"
Products found: {count}
Total available: {total}
Best price product: {best_product}
Marketplace: {marketplace}

Generate a brief, helpful response (1-2 sentences) that:
1. Confirms what was searched
2. Mentions the number of results
3. Highlights the best price if available
4. Uses the SAME LANGUAGE as the user's query

Examples:
- Spanish: "Encontré 20 productos para 'laptop gaming RTX 4070'. El mejor precio es USD 1,299 en eBay."
- English: "Found 20 products for 'gaming laptop RTX 4070'. Best price is USD 1,299 on eBay."

Respond with ONLY the message text."""
