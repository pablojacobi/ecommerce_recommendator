"""Admin configuration for accounts app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
# UserAdmin is generic in django-stubs but not subscriptable at runtime (known issue)
# See: https://github.com/typeddjango/django-stubs/issues/1097
class UserAdmin(BaseUserAdmin):  # type: ignore[type-arg]
    """Admin configuration for custom User model."""

    list_display = ("username", "email", "is_staff", "is_active")
    list_filter = ("is_staff", "is_active", "date_joined")
    search_fields = ("username", "email")
    ordering = ("-date_joined",)


# Add custom fieldsets after class definition to avoid mypy class variable override error
UserAdmin.fieldsets = (
    *tuple(BaseUserAdmin.fieldsets or ()),
    (
        "Preferences",
        {
            "fields": ("preferred_marketplaces",),
        },
    ),
)
