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
    SEARCH_EXTRACTION_PROMPT,
    SYSTEM_PROMPT,
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
        # Map sort order string to enum
        sort_order = None
        sort_str = data.get("sort_order")
        if sort_str:
            sort_mapping = {
                "relevance": SortOrder.RELEVANCE,
                "price_asc": SortOrder.PRICE_ASC,
                "price_desc": SortOrder.PRICE_DESC,
                "newest": SortOrder.NEWEST,
                "best_seller": SortOrder.BEST_SELLER,
            }
            sort_order = sort_mapping.get(sort_str)

        # Parse prices
        min_price = None
        max_price = None
        if data.get("min_price") is not None:
            min_price = Decimal(str(data["min_price"]))
        if data.get("max_price") is not None:
            max_price = Decimal(str(data["max_price"]))

        # Parse keywords
        keywords = tuple(data.get("keywords", []))

        # Parse limit
        limit = min(max(int(data.get("limit", 20)), 1), 100)

        return SearchIntent(
            query=data.get("query", original_query),
            original_query=original_query,
            sort_order=sort_order,
            min_price=min_price,
            max_price=max_price,
            require_free_shipping=bool(data.get("require_free_shipping", False)),
            min_seller_rating=data.get("min_seller_rating"),
            condition=data.get("condition"),
            destination_country=data.get("destination_country"),
            include_import_taxes=bool(data.get("include_import_taxes", False)),
            limit=limit,
            keywords=keywords,
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
