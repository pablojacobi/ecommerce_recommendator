"""API serializers for chat and search."""

from __future__ import annotations

from rest_framework import serializers

from apps.chat.models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    """Serializer for Message model."""

    class Meta:
        """Meta options for MessageSerializer."""

        model = Message
        fields = [
            "id",
            "role",
            "content",
            "search_results",
            "search_params",
            "created_at",
            "is_user_message",
            "is_assistant_message",
            "has_results",
        ]
        read_only_fields = [
            "id",
            "role",
            "search_results",
            "search_params",
            "created_at",
            "is_user_message",
            "is_assistant_message",
            "has_results",
        ]


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for Conversation model."""

    messages = MessageSerializer(many=True, read_only=True)
    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        """Meta options for ConversationSerializer."""

        model = Conversation
        fields = [
            "id",
            "title",
            "selected_marketplaces",
            "created_at",
            "updated_at",
            "is_active",
            "message_count",
            "messages",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "message_count"]


class ConversationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing conversations."""

    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        """Meta options for ConversationListSerializer."""

        model = Conversation
        fields = [
            "id",
            "title",
            "selected_marketplaces",
            "created_at",
            "updated_at",
            "is_active",
            "message_count",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "message_count"]


class ChatMessageInputSerializer(serializers.Serializer):
    """Serializer for chat message input.

    Note: DRF CharField has trim_whitespace=True by default,
    so whitespace-only content becomes empty and fails min_length.
    """

    content = serializers.CharField(
        required=True,
        min_length=1,
        max_length=2000,
        help_text="The user's message or query",
    )
    marketplaces = serializers.ListField(
        child=serializers.CharField(max_length=20),
        required=False,
        default=list,
        help_text="List of marketplace codes to search",
    )


class ProductResultSerializer(serializers.Serializer):
    """Serializer for product search results."""

    id = serializers.CharField()
    marketplace_code = serializers.CharField()
    marketplace_name = serializers.CharField()
    title = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.CharField()
    url = serializers.URLField()
    image_url = serializers.URLField(allow_null=True, required=False)
    seller_name = serializers.CharField(allow_null=True, required=False)
    seller_rating = serializers.FloatField(allow_null=True, required=False)
    condition = serializers.CharField(allow_null=True, required=False)
    shipping_cost = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True, required=False
    )
    free_shipping = serializers.BooleanField(default=False)
    is_best_price = serializers.BooleanField(default=False)
    price_rank = serializers.IntegerField(default=0)


class SearchResultsSerializer(serializers.Serializer):
    """Serializer for aggregated search results."""

    products = ProductResultSerializer(many=True)
    total_count = serializers.IntegerField()
    query = serializers.CharField()
    has_more = serializers.BooleanField()
    successful_marketplaces = serializers.IntegerField()
    failed_marketplaces = serializers.ListField(child=serializers.CharField())


class ChatResponseSerializer(serializers.Serializer):
    """Serializer for chat response."""

    message = MessageSerializer()
    search_results = SearchResultsSerializer(allow_null=True, required=False)


class MarketplaceSerializer(serializers.Serializer):
    """Serializer for marketplace information."""

    code = serializers.CharField()
    name = serializers.CharField()
    country = serializers.CharField()
    is_available = serializers.BooleanField()


class HealthCheckSerializer(serializers.Serializer):
    """Serializer for health check response."""

    status = serializers.CharField()
    version = serializers.CharField()
    services = serializers.DictField(child=serializers.BooleanField())
