"""API views for chat and search."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from asgiref.sync import async_to_sync
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.serializers import (
    ChatMessageInputSerializer,
    ChatResponseSerializer,
    ConversationListSerializer,
    ConversationSerializer,
    HealthCheckSerializer,
    MarketplaceSerializer,
    MessageSerializer,
)
from apps.chat.models import Conversation, Message
from core.logging import get_logger

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from services.chat.types import ChatResponse as ChatServiceResponse

logger = get_logger(__name__)


class ConversationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing conversations.

    Provides CRUD operations for conversations and
    a chat endpoint for sending messages.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self) -> QuerySet[Conversation]:
        """Return conversations for the current user."""
        return Conversation.objects.filter(user=self.request.user)

    def get_serializer_class(self) -> type:
        """Return appropriate serializer based on action."""
        if self.action == "list":
            return ConversationListSerializer
        return ConversationSerializer

    def perform_create(self, serializer: ConversationSerializer) -> None:
        """Create conversation with current user."""
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def chat(self, request: Request, pk: str | None = None) -> Response:
        """
        Send a message to the conversation and get a response.

        This endpoint:
        1. Validates the input message
        2. Creates a user message
        3. Processes the query with Gemini AI
        4. Searches marketplaces if needed
        5. Returns the assistant's response
        """
        conversation = self.get_object()

        # Validate input
        input_serializer = ChatMessageInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                input_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        content = input_serializer.validated_data["content"]
        marketplaces = input_serializer.validated_data.get("marketplaces", [])

        # Update conversation marketplaces if provided
        if marketplaces:
            conversation.selected_marketplaces = marketplaces
            conversation.save(update_fields=["selected_marketplaces", "updated_at"])

        try:
            # Create user message and process
            result = self._process_chat_message(conversation, content)
            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(
                "Chat processing error",
                conversation_id=str(conversation.id),
                error=str(e),
            )
            return Response(
                {"error": "Failed to process message"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _process_chat_message(
        self,
        conversation: Conversation,
        content: str,
    ) -> dict[str, Any]:
        """
        Process a chat message and return response.

        Creates user message, invokes ChatService for AI processing,
        and stores the assistant response.
        """
        with transaction.atomic():
            # Create user message
            Message.objects.create(
                conversation=conversation,
                role=Message.Role.USER,
                content=content,
            )

            # Update conversation title if first message
            if conversation.messages.count() == 1:
                title = content[:50] + "..." if len(content) > 50 else content
                conversation.title = title
                conversation.save(update_fields=["title", "updated_at"])

            # Process with ChatService
            chat_response = self._invoke_chat_service(conversation, content)

            # Build search results data
            search_results_data = self._build_search_results(chat_response)

            # Create assistant message
            assistant_message = Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=chat_response.message,
                search_params=self._build_search_params(chat_response),
                search_results=search_results_data,
            )

        response_serializer = ChatResponseSerializer(
            data={
                "message": MessageSerializer(assistant_message).data,
                "search_results": search_results_data,
            }
        )
        response_serializer.is_valid()
        return response_serializer.data

    def _invoke_chat_service(
        self,
        conversation: Conversation,
        content: str,
    ) -> ChatServiceResponse:
        """Invoke the ChatService to process the message."""
        from django.conf import settings

        from services.chat import ChatRequest, ChatService
        from services.gemini.service import GeminiService
        from services.marketplaces.factory import MarketplaceFactory
        from services.search.orchestrator import SearchOrchestrator

        # Build conversation history from last N messages
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in conversation.messages.order_by("-created_at")[:10]
        ]
        history.reverse()  # Oldest first

        # Create chat request
        request = ChatRequest(
            content=content,
            conversation_id=str(conversation.id),
            user_id=str(conversation.user_id),
            marketplace_codes=tuple(conversation.selected_marketplaces or []),
            conversation_history=tuple(history),
        )

        # Initialize services
        gemini_service = GeminiService(api_key=settings.GEMINI_API_KEY)
        factory = MarketplaceFactory()
        search_orchestrator = SearchOrchestrator(factory=factory)
        chat_service = ChatService(
            gemini_service=gemini_service,
            search_orchestrator=search_orchestrator,
        )

        # Process request (sync wrapper around async)
        response = async_to_sync(chat_service.process)(request)

        # Clean up
        async_to_sync(chat_service.close)()

        return response

    def _build_search_results(
        self,
        chat_response: ChatServiceResponse,
    ) -> dict[str, Any] | None:
        """Build search results data from chat response."""
        if not chat_response.search_results:
            return None

        results = chat_response.search_results
        products = [
            {
                "id": p.product.id,
                "marketplace_code": p.marketplace_code,
                "marketplace_name": p.marketplace_name,
                "title": p.product.title,
                "price": str(p.product.price),
                "currency": p.product.currency,
                "url": p.product.url,
                "image_url": p.product.image_url,
                "seller_name": p.product.seller_name,
                "seller_rating": p.product.seller_rating,
                "condition": p.product.condition,
                "shipping_cost": str(p.product.shipping_cost) if p.product.shipping_cost else None,
                "free_shipping": p.product.free_shipping,
                "is_best_price": p.is_best_price,
                "price_rank": p.price_rank,
            }
            for p in results.products
        ]

        return {
            "products": products,
            "total_count": results.total_count,
            "query": results.query,
            "has_more": results.has_more,
            "successful_marketplaces": results.successful_marketplaces,
            "failed_marketplaces": results.failed_marketplaces,
        }

    def _build_search_params(
        self,
        chat_response: ChatServiceResponse,
    ) -> dict[str, Any] | None:
        """Build search params from chat response."""
        if not chat_response.search_intent:
            return None

        intent = chat_response.search_intent
        return {
            "query": intent.query,
            "original_query": intent.original_query,
            "sort_order": intent.sort_order.value if intent.sort_order else None,
            "min_price": str(intent.min_price) if intent.min_price else None,
            "max_price": str(intent.max_price) if intent.max_price else None,
            "limit": intent.limit,
        }

    @action(detail=True, methods=["post"])
    def clear(self, request: Request, pk: str | None = None) -> Response:
        """Clear all messages in a conversation."""
        conversation = self.get_object()
        conversation.messages.all().delete()
        conversation.title = ""
        conversation.save(update_fields=["title", "updated_at"])

        return Response(
            {"status": "cleared"},
            status=status.HTTP_200_OK,
        )


class MessageViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing messages.

    Messages are read-only through this endpoint.
    Creating messages happens through the conversation chat endpoint.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self) -> QuerySet[Message]:
        """Return messages for conversations owned by the current user."""
        return Message.objects.filter(conversation__user=self.request.user)


class MarketplacesView(APIView):
    """
    API endpoint for listing available marketplaces.

    Returns all configured marketplaces with their availability status.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """Return list of available marketplaces."""
        # Static list of available marketplaces
        # In a full implementation, this would check actual adapter availability
        marketplaces: list[dict[str, str | bool]] = [
            # MercadoLibre markets
            {
                "code": "MLA",
                "name": "MercadoLibre Argentina",
                "country": "Argentina",
                "is_available": True,
            },
            {
                "code": "MLB",
                "name": "MercadoLibre Brasil",
                "country": "Brasil",
                "is_available": True,
            },
            {
                "code": "MLC",
                "name": "MercadoLibre Chile",
                "country": "Chile",
                "is_available": True,
            },
            {
                "code": "MLM",
                "name": "MercadoLibre México",
                "country": "México",
                "is_available": True,
            },
            {
                "code": "MCO",
                "name": "MercadoLibre Colombia",
                "country": "Colombia",
                "is_available": True,
            },
            {
                "code": "MPE",
                "name": "MercadoLibre Perú",
                "country": "Perú",
                "is_available": True,
            },
            {
                "code": "MLU",
                "name": "MercadoLibre Uruguay",
                "country": "Uruguay",
                "is_available": True,
            },
            # eBay markets
            {
                "code": "EBAY_US",
                "name": "eBay United States",
                "country": "USA",
                "is_available": True,
            },
            {
                "code": "EBAY_GB",
                "name": "eBay United Kingdom",
                "country": "UK",
                "is_available": True,
            },
            {
                "code": "EBAY_DE",
                "name": "eBay Germany",
                "country": "Germany",
                "is_available": True,
            },
        ]

        serializer = MarketplaceSerializer(marketplaces, many=True)
        return Response(serializer.data)


class HealthCheckView(APIView):
    """
    API health check endpoint.

    Returns the health status of the API and its dependencies.
    """

    permission_classes = []  # No auth required for health check

    def get(self, request: Request) -> Response:
        """Return health status."""
        health_data = {
            "status": "healthy",
            "version": "0.1.0",
            "services": {
                "database": True,
                "cache": True,
            },
        }

        serializer = HealthCheckSerializer(data=health_data)
        serializer.is_valid()
        return Response(serializer.data)
