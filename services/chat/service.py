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

    # Spanish indicator words for language detection
    _SPANISH_INDICATORS = {
        "busco", "quiero", "necesito", "para", "con", "más", "mejor",
        "barato", "económico", "envío", "precio", "gracias", "hola",
        "computador", "teléfono", "celular", "el", "la", "un", "una",
        "dame", "muéstrame", "encuentra", "ordenar", "filtrar", "usado",
        "nueva", "nuevo", "vendedor", "reputación", "dónde", "cuál",
    }

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
        self._current_user_content: str = ""  # For language detection

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

        # Store user content for language detection in error messages
        self._current_user_content = request.content

        try:
            return await self._process_request(request)
        except Exception as e:
            logger.error(
                "Error processing chat",
                error=str(e),
                conversation_id=request.conversation_id,
            )
            return self._create_error_response(
                "Ocurrió un error procesando tu solicitud. Por favor intenta de nuevo.",
                "An error occurred processing your request. Please try again.",
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
                "No pude entender tu consulta. ¿Podrías reformularla?",
                "I couldn't understand your query. Could you rephrase it?",
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
                "No pude identificar qué producto buscas. ¿Podrías ser más específico?",
                "I couldn't identify what product you're looking for. Could you be more specific?",
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
                "No pude buscar en los marketplaces. Por favor intenta de nuevo.",
                "I couldn't search the marketplaces. Please try again.",
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
        """Handle a refinement intent by modifying the previous search."""
        # If no previous search, fall back to treating it as a new search
        if not context.last_search_intent:
            logger.info("No previous search context, treating refinement as new search")
            return await self._handle_search(request, context)

        # Extract refinement intent
        refinement_result = await self._gemini.extract_refinement_intent(request.content, context)

        if isinstance(refinement_result, Failure):
            logger.warning(
                "Failed to extract refinement",
                error=refinement_result.error.message,
            )
            # Fall back to new search with context
            return await self._handle_search_with_context(request, context)

        refinement = refinement_result.value
        logger.info(
            "Extracted refinement",
            type=refinement.refinement_type,
            filter_criteria=refinement.filter_criteria,
        )

        # Build a modified search based on the previous intent + refinement
        previous_intent = context.last_search_intent

        # Create modified search intent
        from services.gemini.types import SearchIntent
        from services.marketplaces.base import SortOrder
        from decimal import Decimal

        # Apply filter criteria from refinement
        max_price = previous_intent.max_price
        min_price = previous_intent.min_price
        condition = previous_intent.condition
        require_free_shipping = previous_intent.require_free_shipping
        sort_criteria = list(previous_intent.sort_criteria)

        # Parse refinement filters
        filters = refinement.filter_criteria or {}
        if "max_price" in filters:
            max_price = Decimal(str(filters["max_price"]))
        if "min_price" in filters:
            min_price = Decimal(str(filters["min_price"]))
        if "condition" in filters:
            condition = filters["condition"]
        if "free_shipping" in filters and filters["free_shipping"]:
            require_free_shipping = True
        
        # Handle seller rating filter
        min_seller_rating = previous_intent.min_seller_rating
        if "min_seller_rating" in filters:
            min_seller_rating = float(filters["min_seller_rating"])

        # Apply sort preference if specified (adds to sort criteria)
        sort_mapping = {
            "price_asc": SortOrder.PRICE_ASC,
            "price_desc": SortOrder.PRICE_DESC,
            "newest": SortOrder.NEWEST,
            "rating_desc": SortOrder.BEST_SELLER,
        }
        
        if refinement.sort_preference:
            new_sort = sort_mapping.get(refinement.sort_preference)
            if new_sort:
                # Replace primary sort with new preference
                sort_criteria = [new_sort] + [s for s in sort_criteria if s != new_sort]

        # Handle special refinement types
        if refinement.refinement_type == "cheapest":
            sort_criteria = [SortOrder.PRICE_ASC] + [s for s in sort_criteria if s != SortOrder.PRICE_ASC]
        elif refinement.refinement_type == "best_rated":
            sort_criteria = [SortOrder.BEST_SELLER] + [s for s in sort_criteria if s != SortOrder.BEST_SELLER]
            if min_seller_rating is None:
                min_seller_rating = 4.0  # Default to 4+ stars

        modified_intent = SearchIntent(
            query=previous_intent.query,
            original_query=f"{previous_intent.original_query} ({request.content})",
            sort_criteria=tuple(sort_criteria),
            min_price=min_price,
            max_price=max_price,
            require_free_shipping=require_free_shipping,
            min_seller_rating=min_seller_rating,
            condition=condition,
            destination_country=previous_intent.destination_country or request.destination_country,
            include_import_taxes=previous_intent.include_import_taxes,
            limit=previous_intent.limit,
            keywords=previous_intent.keywords,
            ebay_category_id=previous_intent.ebay_category_id,
            meli_category_id=previous_intent.meli_category_id,
        )

        logger.info(
            "Modified search intent for refinement",
            query=modified_intent.query,
            max_price=modified_intent.max_price,
            sort_criteria=modified_intent.sort_criteria,
        )

        # Execute the modified search
        search_request = SearchRequest(
            intent=modified_intent,
            marketplace_codes=request.marketplace_codes,
            user_id=request.user_id,
            destination_country=request.destination_country,
        )

        search_result = await self._search.search(search_request)

        if isinstance(search_result, Failure):
            logger.warning("Refinement search failed", error=search_result.error.message)
            return self._create_error_response(
                "No pude aplicar el filtro. Por favor intenta de nuevo.",
                "I couldn't apply the filter. Please try again.",
            )

        results = search_result.value
        message = self._format_search_response(modified_intent.query, results)

        return ChatResponse(
            message=message,
            intent_type=IntentType.REFINEMENT,
            search_intent=modified_intent,
            search_results=results,
        )

    async def _handle_search_with_context(
        self,
        request: ChatRequest,
        context: ConversationContext,
    ) -> ChatResponse:
        """Handle search using context from previous queries."""
        if not context.last_search_intent:
            return await self._handle_search(request, context)

        # Try to extract what the user wants to filter
        # Combine previous query with new request
        combined_query = f"{context.last_search_intent.query} {request.content}"

        # Create a modified request with the combined query
        from services.chat.types import ChatRequest as CR
        modified_request = CR(
            content=combined_query,
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            marketplace_codes=request.marketplace_codes,
            conversation_history=request.conversation_history,
            destination_country=request.destination_country,
        )

        return await self._handle_search(modified_request, context)

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
        from decimal import Decimal
        from services.gemini.types import SearchIntent
        from services.marketplaces.base import SortOrder
        
        context = ConversationContext(
            selected_marketplaces=list(request.marketplace_codes),
        )

        # Add conversation history and find the last search intent
        last_search_params = None
        results_count = 0
        
        for msg in request.conversation_history:
            if msg.get("role") == "user":
                context.add_user_message(msg.get("content", ""))
            elif msg.get("role") == "assistant":
                context.add_assistant_message(msg.get("content", ""))
                # Track the last search params from assistant messages
                if msg.get("search_params"):
                    last_search_params = msg["search_params"]
                    # Try to get results count from search_results if present
                    results_count = 20  # Default assumption

        # Reconstruct last_search_intent if we have search params
        if last_search_params:
            sort_mapping = {
                "relevance": SortOrder.RELEVANCE,
                "price_asc": SortOrder.PRICE_ASC,
                "price_desc": SortOrder.PRICE_DESC,
                "newest": SortOrder.NEWEST,
                "best_seller": SortOrder.BEST_SELLER,
            }
            
            sort_criteria = tuple(
                sort_mapping[s] for s in last_search_params.get("sort_criteria", [])
                if s in sort_mapping
            )
            
            context.last_search_intent = SearchIntent(
                query=last_search_params.get("query", ""),
                original_query=last_search_params.get("original_query", ""),
                sort_criteria=sort_criteria,
                min_price=Decimal(str(last_search_params["min_price"])) if last_search_params.get("min_price") else None,
                max_price=Decimal(str(last_search_params["max_price"])) if last_search_params.get("max_price") else None,
                condition=last_search_params.get("condition"),
                require_free_shipping=last_search_params.get("require_free_shipping", False),
                min_seller_rating=last_search_params.get("min_seller_rating"),
                limit=last_search_params.get("limit", 20),
                ebay_category_id=last_search_params.get("ebay_category_id"),
                meli_category_id=last_search_params.get("meli_category_id"),
            )
            context.last_results_count = results_count
            
            logger.debug(
                "Reconstructed search context",
                query=context.last_search_intent.query,
                results_count=results_count,
            )

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

    def _is_spanish(self, text: str) -> bool:
        """Detect if text is likely in Spanish based on common words."""
        text_lower = text.lower()
        return any(word in text_lower for word in self._SPANISH_INDICATORS)

    def _create_error_response(
        self, spanish_msg: str, english_msg: str | None = None
    ) -> ChatResponse:
        """Create an error response in the user's language.
        
        Args:
            spanish_msg: Message in Spanish (used if user wrote in Spanish)
            english_msg: Message in English (used otherwise, defaults to english if not provided)
        """
        # Default to English if no english message provided
        if english_msg is None:
            english_msg = spanish_msg  # Fallback
        
        # Choose message based on user's language
        message = spanish_msg if self._is_spanish(self._current_user_content) else english_msg
        
        return ChatResponse(
            message=message,
            error=message,
        )

    async def close(self) -> None:
        """Close service resources."""
        await self._search.close()
