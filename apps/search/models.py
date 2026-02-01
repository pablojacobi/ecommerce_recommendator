"""Models for the search application."""

from __future__ import annotations

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ImportTaxRate(models.Model):
    """
    Import tax rates by country.

    Stores VAT/IVA and customs duty rates for calculating
    estimated import costs when shipping internationally.
    """

    country_code = models.CharField(
        max_length=3,
        unique=True,
        help_text="ISO 3166-1 alpha-2 or alpha-3 country code",
    )
    country_name = models.CharField(
        max_length=100,
        help_text="Full country name",
    )
    vat_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="VAT/IVA rate as percentage (e.g., 19.00 for 19%)",
    )
    customs_duty_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Average customs duty rate as percentage",
    )
    de_minimis_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Value below which no import taxes apply (in USD)",
    )
    currency_code = models.CharField(
        max_length=3,
        default="USD",
        help_text="Local currency code (ISO 4217)",
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Additional notes about import regulations",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this tax rate is currently active",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options for ImportTaxRate model."""

        db_table = "import_tax_rates"
        ordering = ["country_name"]
        verbose_name = "Import Tax Rate"
        verbose_name_plural = "Import Tax Rates"

    def __str__(self) -> str:
        """Return string representation."""
        return f"{self.country_name} ({self.country_code})"

    def calculate_import_cost(
        self,
        product_price_usd: Decimal,
        shipping_cost_usd: Decimal = Decimal("0"),
    ) -> dict[str, Decimal]:
        """
        Calculate estimated import costs for a product.

        Args:
            product_price_usd: Product price in USD.
            shipping_cost_usd: Shipping cost in USD.

        Returns:
            Dictionary with breakdown of costs.
        """
        total_value = product_price_usd + shipping_cost_usd

        # Check de minimis threshold
        if total_value <= self.de_minimis_usd:
            return {
                "product_price": product_price_usd,
                "shipping_cost": shipping_cost_usd,
                "customs_duty": Decimal("0"),
                "vat": Decimal("0"),
                "total": total_value,
            }

        # Calculate customs duty on product value
        customs_duty = product_price_usd * (self.customs_duty_rate / Decimal("100"))

        # Calculate VAT on (product + shipping + customs duty)
        taxable_value = total_value + customs_duty
        vat = taxable_value * (self.vat_rate / Decimal("100"))

        return {
            "product_price": product_price_usd,
            "shipping_cost": shipping_cost_usd,
            "customs_duty": customs_duty.quantize(Decimal("0.01")),
            "vat": vat.quantize(Decimal("0.01")),
            "total": (total_value + customs_duty + vat).quantize(Decimal("0.01")),
        }


class Marketplace(models.Model):
    """
    Marketplace configuration.

    Stores information about supported marketplaces
    (eBay, MercadoLibre by country, etc.).
    """

    class Provider(models.TextChoices):
        """Marketplace provider."""

        EBAY = "ebay", "eBay"
        MERCADOLIBRE = "mercadolibre", "MercadoLibre"

    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Unique marketplace code (e.g., 'EBAY_US', 'MLC')",
    )
    name = models.CharField(
        max_length=100,
        help_text="Display name (e.g., 'eBay USA', 'MercadoLibre Chile')",
    )
    provider = models.CharField(
        max_length=20,
        choices=Provider.choices,
        help_text="Marketplace provider",
    )
    country_code = models.CharField(
        max_length=3,
        help_text="ISO country code",
    )
    country_name = models.CharField(
        max_length=100,
        help_text="Country name for display",
    )
    api_site_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="API site identifier (e.g., 'MLC' for MercadoLibre Chile)",
    )
    currency_code = models.CharField(
        max_length=3,
        default="USD",
        help_text="Default currency code",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this marketplace is currently supported",
    )
    display_order = models.PositiveIntegerField(
        default=0,
        help_text="Order for display in UI (lower = first)",
    )

    class Meta:
        """Meta options for Marketplace model."""

        db_table = "marketplaces"
        ordering = ["display_order", "name"]
        verbose_name = "Marketplace"
        verbose_name_plural = "Marketplaces"

    def __str__(self) -> str:
        """Return string representation."""
        return self.name

    @property
    def is_ebay(self) -> bool:
        """Check if this is an eBay marketplace."""
        return self.provider == self.Provider.EBAY

    @property
    def is_mercadolibre(self) -> bool:
        """Check if this is a MercadoLibre marketplace."""
        return self.provider == self.Provider.MERCADOLIBRE
