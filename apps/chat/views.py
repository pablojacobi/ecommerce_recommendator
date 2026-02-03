"""Views for chat app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from asgiref.sync import async_to_sync
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from apps.chat.models import Conversation, Message
from core.config import get_settings
from core.logging import get_logger

if TYPE_CHECKING:
    from django.http import HttpRequest

logger = get_logger(__name__)


@login_required
def index(request: HttpRequest) -> HttpResponse:
    """Display the chat interface with the most recent conversation."""
    from core.config import get_settings

    config = get_settings()

    # Get all user conversations
    conversations = Conversation.objects.filter(user=request.user).order_by("-updated_at")

    # Get the most recent conversation or create one
    conversation = conversations.first()
    if not conversation:
        conversation = Conversation.objects.create(
            user=request.user,
            title="",  # Will be generated on first message
        )
        conversations = [conversation]

    # Get messages for current conversation
    chat_messages = conversation.messages.order_by("created_at")

    return render(
        request,
        "chat/index.html",
        {
            "conversation": conversation,
            "conversations": conversations,
            "chat_messages": chat_messages,
            "enable_mercadolibre": config.enable_mercadolibre,
        },
    )


@login_required
def new_conversation(request: HttpRequest) -> HttpResponse:
    """Create a new conversation and redirect to it."""
    from django.shortcuts import redirect

    conversation = Conversation.objects.create(
        user=request.user,
        title="",  # Will be generated on first message
    )
    return redirect("chat:conversation", conversation_id=conversation.id)


@login_required
def conversation(request: HttpRequest, conversation_id) -> HttpResponse:
    """Display a specific conversation."""
    from core.config import get_settings

    config = get_settings()
    conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)

    # Get all user conversations for sidebar
    conversations = Conversation.objects.filter(user=request.user).order_by("-updated_at")

    # Get messages for this conversation
    chat_messages = conversation.messages.order_by("created_at")

    return render(
        request,
        "chat/index.html",
        {
            "conversation": conversation,
            "conversations": conversations,
            "chat_messages": chat_messages,
            "enable_mercadolibre": config.enable_mercadolibre,
        },
    )


@login_required
@require_POST
def send_message(request: HttpRequest) -> HttpResponse:
    """Handle sending a message via HTMX."""
    message_text = request.POST.get("message", "").strip()
    conversation_id = request.POST.get("conversation_id", "")
    marketplaces_str = request.POST.get("marketplaces", "")
    destination_country = request.POST.get("destination_country", "")

    if not message_text:
        return HttpResponseBadRequest("Message is required")

    # Parse marketplaces
    marketplaces = [m.strip() for m in marketplaces_str.split(",") if m.strip()]
    if not marketplaces:
        marketplaces = ["EBAY_US", "MLC"]  # Default

    # Get or create conversation
    is_new_conversation = False
    if conversation_id:
        try:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
            # Check if this is the first message (title is empty)
            is_new_conversation = not conversation.title
        except Exception:
            conversation = Conversation.objects.create(
                user=request.user,
                title="",  # Will be generated
            )
            is_new_conversation = True
    else:
        conversation = Conversation.objects.create(
            user=request.user,
            title="",  # Will be generated
        )
        is_new_conversation = True

    # Update conversation marketplaces
    conversation.selected_marketplaces = marketplaces
    conversation.save(update_fields=["selected_marketplaces", "updated_at"])

    # Save user message
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=message_text,
    )

    # Process with ChatService
    try:
        response_data = _process_chat(
            user_id=str(request.user.id),
            conversation_id=str(conversation.id),
            message=message_text,
            marketplaces=tuple(marketplaces),
            destination_country=destination_country or None,
            conversation=conversation,
            generate_title=is_new_conversation,
        )

        # Update conversation title if generated
        if response_data.get("generated_title"):
            conversation.title = response_data["generated_title"]
            conversation.save(update_fields=["title"])

        # Save assistant message with products and search params (ensure JSON serializable)
        products = response_data.get("products", [])
        serializable_products = _make_json_serializable(products)
        search_intent = response_data.get("search_intent")
        
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=response_data["message"],
            search_results={
                "products": serializable_products,
                "has_more": response_data.get("has_more", False),
            } if serializable_products else None,
            search_params=search_intent,  # Persist the search intent for context
        )

        # Render assistant message HTML
        assistant_message_html = render_to_string(
            "chat/partials/assistant_message.html",
            {
                "message": response_data["message"],
                "products": response_data.get("products", []),
                "has_more": response_data.get("has_more", False),
                "conversation_id": str(conversation.id),
            },
            request=request,
        )

    except Exception as e:
        logger.error("Error processing chat", error=str(e))
        # Detect language from message for error response
        is_spanish = _detect_spanish(message_text)
        error_msg = (
            "Lo siento, ocurrió un error procesando tu solicitud. Por favor intenta de nuevo."
            if is_spanish
            else "Sorry, an error occurred processing your request. Please try again."
        )
        assistant_message_html = render_to_string(
            "chat/partials/assistant_message.html",
            {
                "message": error_msg,
                "products": [],
            },
            request=request,
        )

    # Only return assistant message - user message was already added by JavaScript
    return HttpResponse(assistant_message_html)


def _make_json_serializable(obj):
    """Recursively convert Decimal and other non-JSON types to JSON-serializable types."""
    from decimal import Decimal

    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        return str(obj)


def _detect_spanish(text: str) -> bool:
    """Detect if text is likely in Spanish based on common words."""
    spanish_indicators = [
        "busco", "quiero", "necesito", "para", "con", "más", "mejor",
        "barato", "económico", "envío", "precio", "gracias", "hola",
        "laptop", "computador", "teléfono", "celular", "el", "la", "un", "una",
    ]
    text_lower = text.lower()
    return any(word in text_lower for word in spanish_indicators)


def _create_marketplace_factory(config) -> "MarketplaceFactory":
    """Create and configure the marketplace factory with all adapters."""
    from apps.search.models import Marketplace
    from services.marketplaces.ebay.adapter import EbayAdapter
    from services.marketplaces.factory import MarketplaceFactory
    from services.marketplaces.mercadolibre.adapter import MercadoLibreAdapter
    from services.marketplaces.mercadolibre.client import MercadoLibreClient

    factory = MarketplaceFactory()

    # Get all active marketplaces from DB
    active_marketplaces = Marketplace.objects.filter(is_active=True)

    for marketplace in active_marketplaces:
        if marketplace.provider == Marketplace.Provider.EBAY:
            # Create eBay adapter - uses app_id, cert_id, marketplace_id
            adapter = EbayAdapter(
                app_id=config.ebay.app_id,
                cert_id=config.ebay.cert_id.get_secret_value(),
                marketplace_id=marketplace.code,
            )
            factory.register(marketplace.code, adapter)

        elif marketplace.provider == Marketplace.Provider.MERCADOLIBRE:
            # Create MercadoLibre adapter - uses site_id and credentials
            client = MercadoLibreClient(
                site_id=marketplace.api_site_id,
                app_id=config.mercadolibre.app_id if config.mercadolibre.is_configured else None,
                client_secret=config.mercadolibre.client_secret.get_secret_value()
                if config.mercadolibre.is_configured
                else None,
            )
            adapter = MercadoLibreAdapter(site_id=marketplace.api_site_id, client=client)
            factory.register(marketplace.code, adapter)

    logger.info(
        "Marketplace factory initialized",
        registered_count=factory.adapter_count,
        codes=factory.registered_codes,
    )

    return factory


def _process_chat(
    user_id: str,
    conversation_id: str,
    message: str,
    marketplaces: tuple[str, ...],
    destination_country: str | None,
    conversation: Conversation,
    generate_title: bool = False,
) -> dict:
    """Process chat message using ChatService."""
    from services.chat import ChatRequest, ChatService
    from services.gemini.service import GeminiService
    from services.marketplaces.factory import MarketplaceFactory
    from services.search.orchestrator import SearchOrchestrator

    # Build conversation history (include search_params for context)
    history: list[dict] = []
    messages = conversation.messages.order_by("created_at")[:20]
    for msg in messages:
        msg_data = {"role": msg.role, "content": msg.content}
        if msg.search_params:
            msg_data["search_params"] = msg.search_params
        history.append(msg_data)

    # Initialize services
    config = get_settings()
    gemini_service = GeminiService(api_key=config.gemini.api_key.get_secret_value())

    # Generate title if needed
    generated_title = None
    if generate_title:
        generated_title = async_to_sync(gemini_service.generate_title)(message)

    # Create and configure marketplace factory with adapters
    factory = _create_marketplace_factory(config)

    # Get Gemini client for AI-powered product filtering
    gemini_client = gemini_service._get_client()

    search_orchestrator = SearchOrchestrator(factory, gemini_client=gemini_client)
    chat_service = ChatService(gemini_service, search_orchestrator)

    # Create request
    chat_request = ChatRequest(
        content=message,
        conversation_id=conversation_id,
        user_id=user_id,
        marketplace_codes=marketplaces,
        conversation_history=tuple(history),
        destination_country=destination_country,
    )

    # Process async
    response = async_to_sync(chat_service.process)(chat_request)

    # Build response data
    result: dict = {
        "message": response.message,
        "products": [],
        "has_more": False,
        "generated_title": generated_title,
        "search_intent": None,
    }

    # Serialize search intent if available
    if response.search_intent:
        intent = response.search_intent
        result["search_intent"] = {
            "query": intent.query,
            "original_query": intent.original_query,
            "sort_criteria": [str(s.value) for s in intent.sort_criteria] if intent.sort_criteria else [],
            "min_price": float(intent.min_price) if intent.min_price else None,
            "max_price": float(intent.max_price) if intent.max_price else None,
            "condition": intent.condition,
            "require_free_shipping": intent.require_free_shipping,
            "min_seller_rating": intent.min_seller_rating,
            "limit": intent.limit,
            "ebay_category_id": intent.ebay_category_id,
            "meli_category_id": intent.meli_category_id,
        }

    if response.search_results:
        result["has_more"] = response.search_results.has_more
        for enriched in response.search_results.products[:10]:
            product_data = {
                "id": enriched.product.id,
                "title": enriched.product.title,
                "price": float(enriched.product.price),
                "currency": enriched.product.currency,
                "url": enriched.product.url,
                "image_url": enriched.product.image_url,
                "marketplace_code": enriched.marketplace_code,
                "marketplace_name": enriched.marketplace_name,
                "seller_rating": float(enriched.product.seller_rating) if enriched.product.seller_rating else None,
                "shipping_cost": float(enriched.product.shipping_cost) if enriched.product.shipping_cost else None,
                "free_shipping": enriched.product.free_shipping,
                "is_best_price": enriched.is_best_price,
                "tax_info": None,
            }
            if enriched.tax_info:
                product_data["tax_info"] = {
                    "product_price_usd": float(enriched.tax_info.product_price_usd),
                    "shipping_cost_usd": float(enriched.tax_info.shipping_cost_usd),
                    "customs_duty": float(enriched.tax_info.customs_duty),
                    "vat": float(enriched.tax_info.vat),
                    "total_taxes": float(enriched.tax_info.total_taxes),
                    "total_with_taxes": float(enriched.tax_info.total_with_taxes),
                    "de_minimis_applied": enriched.tax_info.de_minimis_applied,
                }
            result["products"].append(product_data)

    return result


@login_required
@require_POST
def load_more(request: HttpRequest) -> HttpResponse:
    """Load more results for current conversation."""
    _ = request  # Will be used for pagination in future
    # For now, return empty - pagination would be implemented here
    return HttpResponse("")
