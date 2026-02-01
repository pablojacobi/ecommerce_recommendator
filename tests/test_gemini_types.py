"""Tests for Gemini AI types."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.gemini.types import (
    ConversationContext,
    IntentType,
    RefinementIntent,
    SearchIntent,
)
from services.marketplaces.base import SortOrder


class TestIntentType:
    """Tests for IntentType enum."""

    def test_intent_types_exist(self) -> None:
        """IntentType should have all expected values."""
        assert IntentType.SEARCH.value == "search"
        assert IntentType.REFINEMENT.value == "refinement"
        assert IntentType.CLARIFICATION.value == "clarification"
        assert IntentType.COMPARISON.value == "comparison"
        assert IntentType.MORE_RESULTS.value == "more_results"

    def test_intent_type_from_string(self) -> None:
        """IntentType can be created from string."""
        assert IntentType("search") == IntentType.SEARCH
        assert IntentType("refinement") == IntentType.REFINEMENT


class TestSearchIntent:
    """Tests for SearchIntent dataclass."""

    def test_create_with_defaults(self) -> None:
        """SearchIntent can be created with minimal args."""
        intent = SearchIntent(query="laptop", original_query="find me a laptop")

        assert intent.query == "laptop"
        assert intent.original_query == "find me a laptop"
        assert intent.sort_order is None
        assert intent.min_price is None
        assert intent.max_price is None
        assert intent.require_free_shipping is False
        assert intent.min_seller_rating is None
        assert intent.condition is None
        assert intent.destination_country is None
        assert intent.include_import_taxes is False
        assert intent.limit == 20
        assert intent.keywords == ()

    def test_create_with_all_fields(self) -> None:
        """SearchIntent can be created with all fields."""
        intent = SearchIntent(
            query="gaming laptop",
            original_query="find gaming laptop under 1000",
            sort_order=SortOrder.PRICE_ASC,
            min_price=Decimal("500"),
            max_price=Decimal("1000"),
            require_free_shipping=True,
            min_seller_rating=4.0,
            condition="new",
            destination_country="CL",
            include_import_taxes=True,
            limit=50,
            keywords=("gaming", "rgb"),
        )

        assert intent.query == "gaming laptop"
        assert intent.sort_order == SortOrder.PRICE_ASC
        assert intent.min_price == Decimal("500")
        assert intent.max_price == Decimal("1000")
        assert intent.require_free_shipping is True
        assert intent.min_seller_rating == 4.0
        assert intent.condition == "new"
        assert intent.destination_country == "CL"
        assert intent.include_import_taxes is True
        assert intent.limit == 50
        assert intent.keywords == ("gaming", "rgb")

    def test_is_frozen(self) -> None:
        """SearchIntent should be immutable."""
        intent = SearchIntent(query="laptop", original_query="laptop")

        with pytest.raises(AttributeError):
            intent.query = "changed"  # type: ignore[misc]


class TestRefinementIntent:
    """Tests for RefinementIntent dataclass."""

    def test_create_with_defaults(self) -> None:
        """RefinementIntent can be created with minimal args."""
        intent = RefinementIntent(
            refinement_type="filter",
            original_query="show only new ones",
        )

        assert intent.refinement_type == "filter"
        assert intent.original_query == "show only new ones"
        assert intent.filter_criteria == {}
        assert intent.sort_preference is None
        assert intent.comparison_criteria is None

    def test_create_with_all_fields(self) -> None:
        """RefinementIntent can be created with all fields."""
        intent = RefinementIntent(
            refinement_type="filter",
            original_query="show cheapest new ones",
            filter_criteria={"condition": "new"},
            sort_preference="price_asc",
            comparison_criteria="price",
        )

        assert intent.filter_criteria == {"condition": "new"}
        assert intent.sort_preference == "price_asc"
        assert intent.comparison_criteria == "price"

    def test_is_frozen(self) -> None:
        """RefinementIntent should be immutable."""
        intent = RefinementIntent(
            refinement_type="filter",
            original_query="test",
        )

        with pytest.raises(AttributeError):
            intent.refinement_type = "changed"  # type: ignore[misc]


class TestConversationContext:
    """Tests for ConversationContext dataclass."""

    def test_create_with_defaults(self) -> None:
        """ConversationContext can be created with defaults."""
        context = ConversationContext()

        assert context.messages == []
        assert context.last_search_intent is None
        assert context.last_results_count == 0
        assert context.current_offset == 0
        assert context.selected_marketplaces == []

    def test_add_user_message(self) -> None:
        """add_user_message should add message with user role."""
        context = ConversationContext()

        context.add_user_message("Hello")

        assert len(context.messages) == 1
        assert context.messages[0] == {"role": "user", "content": "Hello"}

    def test_add_assistant_message(self) -> None:
        """add_assistant_message should add message with assistant role."""
        context = ConversationContext()

        context.add_assistant_message("Hi there")

        assert len(context.messages) == 1
        assert context.messages[0] == {"role": "assistant", "content": "Hi there"}

    def test_get_recent_messages_all(self) -> None:
        """get_recent_messages should return all messages when few."""
        context = ConversationContext()
        context.add_user_message("1")
        context.add_assistant_message("2")
        context.add_user_message("3")

        messages = context.get_recent_messages()

        assert len(messages) == 3

    def test_get_recent_messages_limited(self) -> None:
        """get_recent_messages should limit to most recent."""
        context = ConversationContext()
        for i in range(15):
            context.add_user_message(f"message {i}")

        messages = context.get_recent_messages(limit=5)

        assert len(messages) == 5
        assert messages[0]["content"] == "message 10"
        assert messages[4]["content"] == "message 14"

    def test_clear(self) -> None:
        """clear should reset all fields."""
        context = ConversationContext()
        context.add_user_message("test")
        context.last_search_intent = SearchIntent(query="test", original_query="test")
        context.last_results_count = 10
        context.current_offset = 20

        context.clear()

        assert context.messages == []
        assert context.last_search_intent is None
        assert context.last_results_count == 0
        assert context.current_offset == 0

    def test_is_mutable(self) -> None:
        """ConversationContext should be mutable."""
        context = ConversationContext()

        context.last_results_count = 50

        assert context.last_results_count == 50
