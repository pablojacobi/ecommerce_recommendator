"""Types for chat service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.gemini.types import IntentType, SearchIntent
    from services.search.types import AggregatedResult


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """
    Request for chat processing.

    Attributes:
        content: The user's message content.
        conversation_id: ID of the conversation.
        user_id: ID of the user.
        marketplace_codes: Marketplaces to search.
        conversation_history: Previous messages for context.
    """

    content: str
    conversation_id: str
    user_id: str
    marketplace_codes: tuple[str, ...] = ()
    conversation_history: tuple[dict[str, str], ...] = ()


@dataclass(slots=True)
class ChatResponse:
    """
    Response from chat processing.

    Attributes:
        message: The assistant's text response.
        intent_type: Detected intent type.
        search_intent: Extracted search intent (if applicable).
        search_results: Search results (if search was performed).
        error: Error message if processing failed.
    """

    message: str
    intent_type: IntentType | None = None
    search_intent: SearchIntent | None = None
    search_results: AggregatedResult | None = None
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """Return True if processing was successful."""
        return self.error is None

    @property
    def has_results(self) -> bool:
        """Return True if search results are available."""
        return self.search_results is not None and len(self.search_results.products) > 0


@dataclass(slots=True)
class ProductSummary:
    """
    Summarized product for response formatting.

    Attributes:
        id: Product ID.
        title: Product title.
        price: Formatted price string.
        url: Product URL.
        marketplace: Marketplace name.
        is_best_price: Whether this is the best price.
        image_url: Product image URL.
        seller_rating: Seller rating (0-5).
    """

    id: str
    title: str
    price: str
    url: str
    marketplace: str
    is_best_price: bool = False
    image_url: str | None = None
    seller_rating: float | None = None
