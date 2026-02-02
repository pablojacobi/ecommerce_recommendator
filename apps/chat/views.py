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
    """Display the chat interface."""
    # Get or create a conversation for the user
    conversation = Conversation.objects.filter(user=request.user).order_by("-updated_at").first()

    if not conversation:
        conversation = Conversation.objects.create(
            user=request.user,
            title="Nueva conversación",
        )

    return render(
        request,
        "chat/index.html",
        {
            "conversation_id": str(conversation.id),
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
    if conversation_id:
        try:
            conversation = get_object_or_404(Conversation, id=conversation_id, user=request.user)
        except Exception:
            conversation = Conversation.objects.create(
                user=request.user,
                title=message_text[:50],
            )
    else:
        conversation = Conversation.objects.create(
            user=request.user,
            title=message_text[:50],
        )

    # Update conversation marketplaces
    conversation.selected_marketplaces = marketplaces
    conversation.save(update_fields=["selected_marketplaces", "updated_at"])

    # Save user message
    Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content=message_text,
    )

    # Render user message HTML
    user_message_html = render_to_string(
        "chat/partials/user_message.html",
        {"message": message_text},
        request=request,
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
        )

        # Save assistant message
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=response_data["message"],
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
        assistant_message_html = render_to_string(
            "chat/partials/assistant_message.html",
            {
                "message": (
                    "Lo siento, ocurrió un error procesando tu solicitud. "
                    "Por favor intenta de nuevo."
                ),
                "products": [],
            },
            request=request,
        )

    return HttpResponse(user_message_html + assistant_message_html)


def _process_chat(
    user_id: str,
    conversation_id: str,
    message: str,
    marketplaces: tuple[str, ...],
    destination_country: str | None,
    conversation: Conversation,
) -> dict:
    """Process chat message using ChatService."""
    from services.chat import ChatRequest, ChatService
    from services.gemini.service import GeminiService
    from services.marketplaces.factory import MarketplaceFactory
    from services.search.orchestrator import SearchOrchestrator

    # Build conversation history
    history: list[dict[str, str]] = []
    messages = conversation.messages.order_by("created_at")[:20]
    for msg in messages:
        history.append({"role": msg.role, "content": msg.content})

    # Initialize services
    config = get_settings()
    gemini_service = GeminiService(api_key=config.gemini.api_key.get_secret_value())
    factory = MarketplaceFactory()
    search_orchestrator = SearchOrchestrator(factory)
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
    }

    if response.search_results:
        result["has_more"] = response.search_results.has_more
        for enriched in response.search_results.products[:10]:
            product_data = {
                "id": enriched.product.id,
                "title": enriched.product.title,
                "price": enriched.product.price,
                "currency": enriched.product.currency,
                "url": enriched.product.url,
                "image_url": enriched.product.image_url,
                "marketplace_code": enriched.marketplace_code,
                "marketplace_name": enriched.marketplace_name,
                "seller_rating": enriched.product.seller_rating,
                "shipping_cost": enriched.product.shipping_cost,
                "free_shipping": enriched.product.free_shipping,
                "is_best_price": enriched.is_best_price,
                "tax_info": None,
            }
            if enriched.tax_info:
                product_data["tax_info"] = {
                    "customs_duty": enriched.tax_info.customs_duty,
                    "vat": enriched.tax_info.vat,
                    "total_taxes": enriched.tax_info.total_taxes,
                    "total_with_taxes": enriched.tax_info.total_with_taxes,
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
