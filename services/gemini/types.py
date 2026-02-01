"""Types for Gemini AI service."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from decimal import Decimal

    from services.marketplaces.base import SortOrder


class IntentType(str, Enum):
    """Types of user intents."""

    SEARCH = "search"
    REFINEMENT = "refinement"
    CLARIFICATION = "clarification"
    COMPARISON = "comparison"
    MORE_RESULTS = "more_results"


@dataclass(frozen=True, slots=True)
class SearchIntent:
    """
    Represents a user's search intent extracted from natural language.

    Attributes:
        query: The main search query to send to marketplaces.
        sort_order: Desired sort order (relevance, price_asc, etc.).
        min_price: Minimum price filter.
        max_price: Maximum price filter.
        require_free_shipping: Whether to filter for free shipping.
        min_seller_rating: Minimum seller rating (0-5).
        condition: Product condition filter (new, used, refurbished).
        destination_country: For shipping cost calculations.
        include_import_taxes: Whether to calculate import taxes.
        limit: Number of results requested.
        keywords: Additional keywords extracted for filtering.
        original_query: The original user query.
    """

    query: str
    original_query: str
    sort_order: SortOrder | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    require_free_shipping: bool = False
    min_seller_rating: float | None = None
    condition: str | None = None
    destination_country: str | None = None
    include_import_taxes: bool = False
    limit: int = 20
    keywords: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RefinementIntent:
    """
    Represents a refinement of previous search results.

    Attributes:
        refinement_type: Type of refinement (filter, sort, compare).
        filter_criteria: Criteria to filter results.
        sort_preference: New sort preference.
        comparison_criteria: For comparing products.
        original_query: The original refinement request.
    """

    refinement_type: str
    original_query: str
    filter_criteria: dict[str, str] = field(default_factory=dict)
    sort_preference: str | None = None
    comparison_criteria: str | None = None


@dataclass(slots=True)
class ConversationContext:
    """
    Maintains context for a conversation with the AI.

    Attributes:
        messages: History of messages in the conversation.
        last_search_intent: The most recent search intent.
        last_results_count: Number of results from last search.
        current_offset: Current pagination offset.
        selected_marketplaces: Marketplaces being searched.
    """

    messages: list[dict[str, str]] = field(default_factory=list)
    last_search_intent: SearchIntent | None = None
    last_results_count: int = 0
    current_offset: int = 0
    selected_marketplaces: list[str] = field(default_factory=list)

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation."""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation."""
        self.messages.append({"role": "assistant", "content": content})

    def get_recent_messages(self, limit: int = 10) -> list[dict[str, str]]:
        """Get the most recent messages."""
        return self.messages[-limit:] if len(self.messages) > limit else self.messages

    def clear(self) -> None:
        """Clear the conversation context."""
        self.messages.clear()
        self.last_search_intent = None
        self.last_results_count = 0
        self.current_offset = 0
