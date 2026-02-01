"""Admin configuration for search app."""

from django.contrib import admin

from .models import ImportTaxRate, Marketplace


@admin.register(ImportTaxRate)
class ImportTaxRateAdmin(admin.ModelAdmin):
    """Admin configuration for ImportTaxRate model."""

    list_display = (
        "country_name",
        "country_code",
        "vat_rate",
        "customs_duty_rate",
        "de_minimis_usd",
        "is_active",
    )
    list_filter = ("is_active", "currency_code")
    search_fields = ("country_name", "country_code")
    readonly_fields = ("updated_at",)
    ordering = ("country_name",)


@admin.register(Marketplace)
class MarketplaceAdmin(admin.ModelAdmin):
    """Admin configuration for Marketplace model."""

    list_display = (
        "code",
        "name",
        "provider",
        "country_name",
        "currency_code",
        "is_active",
        "display_order",
    )
    list_filter = ("provider", "is_active")
    search_fields = ("code", "name", "country_name")
    ordering = ("display_order", "name")
