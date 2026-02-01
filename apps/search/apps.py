"""Search app configuration."""

from django.apps import AppConfig


class SearchConfig(AppConfig):
    """Configuration for the search application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.search"
    verbose_name = "Search"
