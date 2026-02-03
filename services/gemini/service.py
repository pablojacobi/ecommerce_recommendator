"""Gemini AI service for query interpretation."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from core.logging import get_logger
from core.result import Failure, Result, failure, success
from services.gemini.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    REFINEMENT_PROMPT,
    RESPONSE_GENERATION_PROMPT,
    SEARCH_EXTRACTION_PROMPT,
    SYSTEM_PROMPT,
    TITLE_GENERATION_PROMPT,
)
from services.gemini.types import (
    ConversationContext,
    IntentType,
    RefinementIntent,
    SearchIntent,
)
from services.marketplaces.base import SortOrder

if TYPE_CHECKING:
    from google.genai import Client

logger = get_logger(__name__)


class GeminiError(Exception):
    """Base exception for Gemini service errors."""

    def __init__(self, message: str, details: str | None = None) -> None:
        """Initialize GeminiError."""
        super().__init__(message)
        self.message = message
        self.details = details


class GeminiService:
    """
    Service for interpreting user queries using Google Gemini AI.

    Extracts structured search parameters from natural language queries
    and handles conversational refinements.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
    ) -> None:
        """
        Initialize Gemini service.

        Args:
            api_key: Google AI API key.
            model: Gemini model to use.

        Raises:
            ValueError: If api_key is empty.
        """
        if not api_key:
            msg = "API key is required"
            raise ValueError(msg)

        self._api_key = api_key
        self._model = model
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Get or create the Gemini client."""
        if self._client is None:
            from google import genai  # Lazy import to avoid import errors

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def extract_search_intent(
        self,
        query: str,
    ) -> Result[SearchIntent, GeminiError]:
        """
        Extract search intent from a user query.

        Args:
            query: The user's natural language query.

        Returns:
            Result containing SearchIntent or GeminiError.
        """
        if not query or not query.strip():
            return failure(GeminiError("Query cannot be empty"))

        prompt = SEARCH_EXTRACTION_PROMPT.format(query=query)

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.1,  # Low temperature for consistent extraction
                },
            )

            if not response.text:
                logger.error("Empty response from Gemini")
                return failure(GeminiError("Empty response from AI"))

            # Parse JSON response
            parsed = self._parse_json_response(response.text)
            if isinstance(parsed, Failure):
                return failure(parsed.error)

            intent = self._build_search_intent(parsed.value, query)
            return success(intent)

        except Exception as e:
            logger.error("Gemini API error", error=str(e))
            return failure(GeminiError("Failed to process query", details=str(e)))

    async def extract_refinement_intent(
        self,
        refinement_query: str,
        context: ConversationContext,
    ) -> Result[RefinementIntent, GeminiError]:
        """
        Extract refinement intent from a follow-up query.

        Args:
            refinement_query: The user's refinement request.
            context: The conversation context.

        Returns:
            Result containing RefinementIntent or GeminiError.
        """
        if not refinement_query or not refinement_query.strip():
            return failure(GeminiError("Refinement query cannot be empty"))

        previous_query = (
            context.last_search_intent.original_query
            if context.last_search_intent
            else "No previous search"
        )

        prompt = REFINEMENT_PROMPT.format(
            previous_query=previous_query,
            results_count=context.last_results_count,
            refinement_query=refinement_query,
        )

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.1,
                },
            )

            if not response.text:
                logger.error("Empty response from Gemini")
                return failure(GeminiError("Empty response from AI"))

            parsed = self._parse_json_response(response.text)
            if isinstance(parsed, Failure):
                return failure(parsed.error)

            intent = self._build_refinement_intent(parsed.value, refinement_query)
            return success(intent)

        except Exception as e:
            logger.error("Gemini API error", error=str(e))
            return failure(GeminiError("Failed to process refinement", details=str(e)))

    async def classify_intent(
        self,
        message: str,
        context: ConversationContext,
    ) -> Result[IntentType, GeminiError]:
        """
        Classify the type of user intent.

        Args:
            message: The user's message.
            context: The conversation context.

        Returns:
            Result containing IntentType or GeminiError.
        """
        if not message or not message.strip():
            return failure(GeminiError("Message cannot be empty"))

        context_summary = self._build_context_summary(context)
        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            context_summary=context_summary,
            message=message,
        )

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "temperature": 0.1,
                },
            )

            if not response.text:
                return failure(GeminiError("Empty response from AI"))

            parsed = self._parse_json_response(response.text)
            if isinstance(parsed, Failure):
                return failure(parsed.error)

            intent_str = parsed.value.get("intent_type", "search")
            return success(IntentType(intent_str))

        except ValueError:
            # Invalid intent type, default to search
            return success(IntentType.SEARCH)
        except Exception as e:
            logger.error("Gemini API error", error=str(e))
            return failure(GeminiError("Failed to classify intent", details=str(e)))

    def _parse_json_response(self, response_text: str) -> Result[dict[str, Any], GeminiError]:
        """Parse JSON from Gemini response."""
        # Clean up response - remove markdown code blocks if present
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            data: dict[str, Any] = json.loads(text)
            return success(data)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse Gemini response", response=text, error=str(e))
            return failure(GeminiError("Invalid JSON response from AI", details=str(e)))

    def _build_search_intent(
        self,
        data: dict[str, Any],
        original_query: str,
    ) -> SearchIntent:
        """Build SearchIntent from parsed data."""
        sort_mapping = {
            "relevance": SortOrder.RELEVANCE,
            "price_asc": SortOrder.PRICE_ASC,
            "price_desc": SortOrder.PRICE_DESC,
            "newest": SortOrder.NEWEST,
            "best_seller": SortOrder.BEST_SELLER,
        }
        
        # Parse sort criteria (supports N sort orders)
        sort_criteria: list[SortOrder] = []
        raw_criteria = data.get("sort_criteria") or []
        
        # Handle both old format (sort_order/secondary_sort_order) and new format (sort_criteria array)
        if not raw_criteria:
            # Fallback to old format for backwards compatibility
            if data.get("sort_order"):
                sort_order = sort_mapping.get(data["sort_order"])
                if sort_order:
                    sort_criteria.append(sort_order)
            if data.get("secondary_sort_order"):
                secondary = sort_mapping.get(data["secondary_sort_order"])
                if secondary:
                    sort_criteria.append(secondary)
        else:
            # New format: array of sort criteria
            for sort_str in raw_criteria:
                if sort_str and sort_str in sort_mapping:
                    sort_criteria.append(sort_mapping[sort_str])

        # Parse prices
        min_price = None
        max_price = None
        if data.get("min_price") is not None:
            min_price = Decimal(str(data["min_price"]))
        if data.get("max_price") is not None:
            max_price = Decimal(str(data["max_price"]))

        # Parse keywords
        keywords = tuple(data.get("keywords") or [])

        # Parse limit (handle null from Gemini)
        raw_limit = data.get("limit")
        limit = min(max(int(raw_limit) if raw_limit is not None else 20, 1), 100)

        # Parse category IDs
        ebay_category_id = data.get("ebay_category_id")
        meli_category_id = data.get("meli_category_id")

        return SearchIntent(
            query=data.get("query", original_query),
            original_query=original_query,
            sort_criteria=tuple(sort_criteria),
            min_price=min_price,
            max_price=max_price,
            require_free_shipping=bool(data.get("require_free_shipping", False)),
            min_seller_rating=data.get("min_seller_rating"),
            condition=data.get("condition"),
            destination_country=data.get("destination_country"),
            include_import_taxes=bool(data.get("include_import_taxes", False)),
            limit=limit,
            keywords=keywords,
            ebay_category_id=ebay_category_id,
            meli_category_id=meli_category_id,
        )

    def _build_refinement_intent(
        self,
        data: dict[str, Any],
        original_query: str,
    ) -> RefinementIntent:
        """Build RefinementIntent from parsed data."""
        return RefinementIntent(
            refinement_type=data.get("refinement_type", "filter"),
            original_query=original_query,
            filter_criteria=data.get("filter_criteria", {}),
            sort_preference=data.get("sort_preference"),
            comparison_criteria=data.get("comparison_criteria"),
        )

    def _build_context_summary(self, context: ConversationContext) -> str:
        """Build a summary of the conversation context."""
        if not context.last_search_intent:
            return "No previous search"

        return (
            f"Previous search: '{context.last_search_intent.original_query}' "
            f"with {context.last_results_count} results"
        )

    async def generate_title(self, message: str) -> str:
        """
        Generate a conversation title from the first message.

        Args:
            message: The user's first message.

        Returns:
            A short title for the conversation (max 30 chars).
        """
        if not message or not message.strip():
            return "New conversation"

        prompt = TITLE_GENERATION_PROMPT.format(message=message)

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"temperature": 0.3},
            )

            if response.text:
                title = response.text.strip()[:30]
                return title if title else "New conversation"
            return "New conversation"

        except Exception as e:
            logger.warning("Failed to generate title", error=str(e))
            # Fallback: use first 30 chars of message
            return message[:30].strip() if len(message) > 30 else message

    async def generate_response(
        self,
        query: str,
        count: int,
        total: int,
        best_product: str | None = None,
        marketplace: str | None = None,
    ) -> str:
        """
        Generate a response message for search results.

        Args:
            query: The search query used.
            count: Number of products found.
            total: Total available products.
            best_product: Description of the best price product.
            marketplace: Name of the marketplace.

        Returns:
            A friendly response message in the user's language.
        """
        prompt = RESPONSE_GENERATION_PROMPT.format(
            query=query,
            count=count,
            total=total,
            best_product=best_product or "N/A",
            marketplace=marketplace or "multiple marketplaces",
        )

        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"temperature": 0.5},
            )

            if response.text:
                return response.text.strip()

            # Fallback response
            return f"Found {count} products for '{query}'."

        except Exception as e:
            logger.warning("Failed to generate response", error=str(e))
            return f"Found {count} products for '{query}'."

    async def healthcheck(self) -> bool:
        """
        Check if the Gemini API is available.

        Returns:
            True if API is healthy, False otherwise.
        """
        try:
            client = self._get_client()
            # Try a simple generation to verify API is working
            response = client.models.generate_content(
                model=self._model,
                contents="Say 'ok'",
                config={"temperature": 0},
            )
            return bool(response.text)
        except Exception:
            return False
