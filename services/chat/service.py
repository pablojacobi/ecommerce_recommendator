"""Chat service for orchestrating AI and search."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.logging import get_logger
from core.result import Failure
from services.chat.types import ChatRequest, ChatResponse
from services.gemini.types import ConversationContext, IntentType
from services.search.types import AggregatedResult, SearchRequest

if TYPE_CHECKING:
    from services.gemini.service import GeminiService
    from services.search.orchestrator import SearchOrchestrator

logger = get_logger(__name__)


class ChatServiceError(Exception):
    """Base exception for chat service errors."""


class ChatService:
    """
    Orchestrates chat interactions with AI and product search.

    This service:
    1. Classifies user intent using Gemini AI
    2. Extracts search parameters from natural language
    3. Searches marketplaces using SearchOrchestrator
    4. Formats responses with product recommendations
    """

    def __init__(
        self,
        gemini_service: GeminiService,
        search_orchestrator: SearchOrchestrator,
    ) -> None:
        """
        Initialize the chat service.

        Args:
            gemini_service: Service for AI interactions.
            search_orchestrator: Service for marketplace searches.
        """
        self._gemini = gemini_service
        self._search = search_orchestrator

    async def process(self, request: ChatRequest) -> ChatResponse:
        """
        Process a chat message and return a response.

        Args:
            request: The chat request containing user message and context.

        Returns:
            ChatResponse with AI message and optional search results.
        """
        logger.info(
            "Processing chat request",
            conversation_id=request.conversation_id,
            content_length=len(request.content),
            marketplaces=request.marketplace_codes,
            destination_country=request.destination_country,
        )

        try:
            return await self._process_request(request)
        except Exception as e:
            logger.error(
                "Error processing chat",
                error=str(e),
                conversation_id=request.conversation_id,
            )
            return self._create_error_response(
                "Ocurrió un error procesando tu solicitud. Por favor intenta de nuevo."
            )

    async def _process_request(self, request: ChatRequest) -> ChatResponse:
        """Process the request after logging."""
        # Build conversation context
        context = self._build_context(request)

        # Classify intent
        intent_result = await self._gemini.classify_intent(request.content, context)

        if isinstance(intent_result, Failure):
            logger.warning(
                "Failed to classify intent",
                error=intent_result.error.message,
            )
            return self._create_error_response(
                "No pude entender tu consulta. ¿Podrías reformularla?"
            )

        intent_type = intent_result.value
        logger.debug("Classified intent", intent_type=intent_type.value)

        # Dispatch to appropriate handler
        return await self._dispatch_intent(intent_type, request, context)

    async def _dispatch_intent(
        self,
        intent_type: IntentType,
        request: ChatRequest,
        context: ConversationContext,
    ) -> ChatResponse:
        """Dispatch to the appropriate intent handler."""
        handlers = {
            IntentType.SEARCH: self._handle_search,
            IntentType.REFINEMENT: self._handle_refinement,
            IntentType.MORE_RESULTS: self._handle_more_results,
        }

        handler = handlers.get(intent_type)
        if handler:
            return await handler(request, context)

        if intent_type == IntentType.CLARIFICATION:
            return self._handle_clarification(request)

        # Default: treat as search
        return await self._handle_search(request, context)

    async def _handle_search(
        self,
        request: ChatRequest,
        context: ConversationContext,
    ) -> ChatResponse:
        """Handle a search intent."""
        _ = context  # Will be used for context-aware search in future
        # Extract search intent
        intent_result = await self._gemini.extract_search_intent(request.content)

        if isinstance(intent_result, Failure):
            logger.warning(
                "Failed to extract search intent",
                error=intent_result.error.message,
            )
            return self._create_error_response(
                "No pude identificar qué producto buscas. ¿Podrías ser más específico?"
            )

        search_intent = intent_result.value
        logger.info(
            "Extracted search intent",
            query=search_intent.query,
            sort_order=search_intent.sort_order,
            limit=search_intent.limit,
        )

        # Check if marketplaces are selected
        if not request.marketplace_codes:
            return ChatResponse(
                message="Por favor selecciona al menos un marketplace "
                "(MercadoLibre o eBay) para buscar productos.",
                intent_type=IntentType.SEARCH,
                search_intent=search_intent,
            )

        # Build search request
        search_request = SearchRequest(
            intent=search_intent,
            marketplace_codes=request.marketplace_codes,
            user_id=request.user_id,
            destination_country=request.destination_country,
        )

        # Execute search
        search_result = await self._search.search(search_request)

        if isinstance(search_result, Failure):
            logger.warning(
                "Search failed",
                error=search_result.error.message,
            )
            return self._create_error_response(
                "No pude buscar en los marketplaces. Por favor intenta de nuevo."
            )

        results = search_result.value

        # Format response message
        message = self._format_search_response(search_intent.query, results)

        return ChatResponse(
            message=message,
            intent_type=IntentType.SEARCH,
            search_intent=search_intent,
            search_results=results,
        )

    async def _handle_refinement(
        self,
        request: ChatRequest,
        context: ConversationContext,
    ) -> ChatResponse:
        """Handle a refinement intent."""
        # Extract refinement intent
        refinement_result = await self._gemini.extract_refinement_intent(request.content, context)

        if isinstance(refinement_result, Failure):
            logger.warning(
                "Failed to extract refinement",
                error=refinement_result.error.message,
            )
            # Fall back to new search
            return await self._handle_search(request, context)

        refinement = refinement_result.value
        logger.info(
            "Extracted refinement",
            type=refinement.refinement_type,
        )

        # For now, treat refinements as new searches with modifications
        # Full refinement logic would reuse previous results
        return await self._handle_search(request, context)

    async def _handle_more_results(
        self,
        request: ChatRequest,
        context: ConversationContext,
    ) -> ChatResponse:
        """Handle a request for more results."""
        if not context.last_search_intent:
            return ChatResponse(
                message="No tengo una búsqueda previa. ¿Qué producto te gustaría buscar?",
                intent_type=IntentType.MORE_RESULTS,
            )

        # Re-execute search with increased offset
        # For now, just redo the search
        return await self._handle_search(request, context)

    def _handle_clarification(self, request: ChatRequest) -> ChatResponse:
        """Handle a clarification request."""
        _ = request  # Will be used for context-aware clarifications
        return ChatResponse(
            message="Claro, ¿qué información adicional necesitas? "
            "Puedo ayudarte a buscar productos, comparar precios, "
            "o filtrar resultados.",
            intent_type=IntentType.CLARIFICATION,
        )

    def _build_context(self, request: ChatRequest) -> ConversationContext:
        """Build conversation context from request."""
        context = ConversationContext(
            selected_marketplaces=list(request.marketplace_codes),
        )

        # Add conversation history
        for msg in request.conversation_history:
            if msg.get("role") == "user":
                context.add_user_message(msg.get("content", ""))
            elif msg.get("role") == "assistant":
                context.add_assistant_message(msg.get("content", ""))

        return context

    def _format_search_response(
        self,
        query: str,
        results: AggregatedResult,
    ) -> str:
        """Format a search response message."""
        if not results.products:
            failed = results.failed_marketplaces
            if failed:
                return (
                    f"No encontré resultados para '{query}'. "
                    f"Algunos marketplaces tuvieron problemas: {', '.join(failed)}. "
                    "¿Quieres intentar con otros términos?"
                )
            return (
                f"No encontré resultados para '{query}'. "
                "¿Quieres intentar con otros términos de búsqueda?"
            )

        count = len(results.products)
        total = results.total_count
        marketplaces = results.successful_marketplaces

        response_parts = [f"Encontré {count} productos para '{query}'"]

        if total > count:
            response_parts.append(f" (de {total} disponibles)")

        response_parts.append(f" en {marketplaces} marketplace{'s' if marketplaces > 1 else ''}.")

        if results.has_more:
            response_parts.append(" Si quieres ver más resultados, solo dímelo.")

        # Add best price highlight if available
        best_price_product = next(
            (p for p in results.products if p.is_best_price),
            None,
        )
        if best_price_product:
            product = best_price_product.product
            price_text = f"{product.currency} {product.price:,.0f}"

            # Add tax info if available
            if best_price_product.tax_info:
                tax_info = best_price_product.tax_info
                price_text = (
                    f"{product.currency} {product.price:,.0f} "
                    f"(+ USD {tax_info.total_taxes:,.2f} impuestos = "
                    f"USD {tax_info.total_with_taxes:,.2f} total)"
                )
                if tax_info.de_minimis_applied:
                    price_text += " [exento de impuestos]"

            response_parts.append(
                f"\n\n💰 Mejor precio: {product.title[:50]}... "
                f"a {price_text} "
                f"en {best_price_product.marketplace_name}."
            )

        return "".join(response_parts)

    def _create_error_response(self, message: str) -> ChatResponse:
        """Create an error response."""
        return ChatResponse(
            message=message,
            error=message,
        )

    async def close(self) -> None:
        """Close service resources."""
        await self._search.close()
