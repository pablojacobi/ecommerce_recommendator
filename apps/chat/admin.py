"""Admin configuration for chat app."""

from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    """Inline admin for messages in a conversation."""

    model = Message
    extra = 0
    readonly_fields = ("id", "created_at")
    fields = ("role", "content", "created_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Admin configuration for Conversation model."""

    list_display = ("id", "user", "title", "message_count", "is_active", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("title", "user__username", "user__email")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [MessageInline]
    date_hierarchy = "created_at"

    def message_count(self, obj: Conversation) -> int:
        """Return number of messages in conversation."""
        return obj.message_count

    message_count.short_description = "Messages"  # type: ignore[attr-defined]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin configuration for Message model."""

    list_display = ("id", "conversation", "role", "short_content", "has_results", "created_at")
    list_filter = ("role", "created_at")
    search_fields = ("content", "conversation__title")
    readonly_fields = ("id", "created_at")
    date_hierarchy = "created_at"

    def short_content(self, obj: Message) -> str:
        """Return truncated content for display."""
        return obj.content[:50] + "..." if len(obj.content) > 50 else obj.content

    short_content.short_description = "Content"  # type: ignore[attr-defined]

    def has_results(self, obj: Message) -> bool:
        """Return whether message has search results."""
        return obj.has_results

    has_results.boolean = True  # type: ignore[attr-defined]
    has_results.short_description = "Has Results"  # type: ignore[attr-defined]
