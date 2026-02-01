"""Tax calculation service."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from core.logging import get_logger
from core.result import Result, success
from services.taxes.types import TaxBreakdown, TaxCalculationRequest

if TYPE_CHECKING:
    from apps.search.models import ImportTaxRate

logger = get_logger(__name__)


class TaxCalculatorError(Exception):
    """Error during tax calculation."""

    def __init__(self, message: str) -> None:
        """Initialize with error message."""
        self.message = message
        super().__init__(message)


# Simple exchange rates to USD (would be fetched from API in production)
# These are approximate rates for estimation purposes
EXCHANGE_RATES_TO_USD: dict[str, Decimal] = {
    "USD": Decimal("1.0"),
    "CLP": Decimal("0.0011"),  # ~900 CLP = 1 USD
    "ARS": Decimal("0.0011"),  # ~900 ARS = 1 USD (volatile)
    "MXN": Decimal("0.058"),  # ~17 MXN = 1 USD
    "COP": Decimal("0.00025"),  # ~4000 COP = 1 USD
    "PEN": Decimal("0.27"),  # ~3.7 PEN = 1 USD
    "BRL": Decimal("0.20"),  # ~5 BRL = 1 USD
    "UYU": Decimal("0.025"),  # ~40 UYU = 1 USD
    "EUR": Decimal("1.08"),  # ~0.93 EUR = 1 USD
    "GBP": Decimal("1.27"),  # ~0.79 GBP = 1 USD
    "CAD": Decimal("0.74"),  # ~1.35 CAD = 1 USD
    "AUD": Decimal("0.65"),  # ~1.54 AUD = 1 USD
}


class TaxCalculatorService:
    """
    Service for calculating import taxes.

    Uses ImportTaxRate model data to estimate import costs
    for international purchases.
    """

    def __init__(self, use_cache: bool = True) -> None:
        """
        Initialize the tax calculator service.

        Args:
            use_cache: Whether to cache tax rates (default True).
        """
        self._use_cache = use_cache
        self._cache: dict[str, ImportTaxRate] = {}

    def calculate(
        self,
        request: TaxCalculationRequest,
    ) -> Result[TaxBreakdown, TaxCalculatorError]:
        """
        Calculate import taxes for a purchase.

        Args:
            request: Tax calculation request with product details.

        Returns:
            Result containing TaxBreakdown or TaxCalculatorError.
        """
        logger.debug(
            "Calculating taxes",
            destination=request.destination_country,
            product_price=str(request.product_price),
            currency=request.source_currency,
        )

        # Convert to USD
        product_usd = self._convert_to_usd(
            request.product_price,
            request.source_currency,
        )
        shipping_usd = self._convert_to_usd(
            request.shipping_cost,
            request.source_currency,
        )

        # Get tax rate for destination
        tax_rate = self._get_tax_rate(request.destination_country)

        if tax_rate is None:
            logger.info(
                "No tax data for country",
                country=request.destination_country,
            )
            return success(
                TaxBreakdown.from_no_taxes(
                    product_price_usd=product_usd,
                    shipping_cost_usd=shipping_usd,
                    destination_country=request.destination_country,
                    destination_country_name=request.destination_country,
                    notes="No hay datos de impuestos disponibles para este país.",
                )
            )

        # Calculate using the model's method
        cost_breakdown = tax_rate.calculate_import_cost(
            product_price_usd=product_usd,
            shipping_cost_usd=shipping_usd,
        )

        # Check if de minimis was applied
        total_value = product_usd + shipping_usd
        de_minimis_applied = total_value <= tax_rate.de_minimis_usd

        return success(
            TaxBreakdown(
                product_price_usd=cost_breakdown["product_price"],
                shipping_cost_usd=cost_breakdown["shipping_cost"],
                customs_duty=cost_breakdown["customs_duty"],
                vat=cost_breakdown["vat"],
                total_taxes=cost_breakdown["customs_duty"] + cost_breakdown["vat"],
                total_cost=cost_breakdown["total"],
                destination_country=tax_rate.country_code,
                destination_country_name=tax_rate.country_name,
                vat_rate=tax_rate.vat_rate,
                customs_duty_rate=tax_rate.customs_duty_rate,
                de_minimis_applied=de_minimis_applied,
                is_estimated=True,
                notes=tax_rate.notes,
            )
        )

    def calculate_batch(
        self,
        requests: list[TaxCalculationRequest],
    ) -> list[Result[TaxBreakdown, TaxCalculatorError]]:
        """
        Calculate taxes for multiple requests.

        Args:
            requests: List of tax calculation requests.

        Returns:
            List of Results, one per request.
        """
        return [self.calculate(req) for req in requests]

    def get_supported_countries(self) -> list[dict[str, str]]:
        """
        Get list of countries with tax data.

        Returns:
            List of dicts with country_code and country_name.
        """
        from apps.search.models import ImportTaxRate

        rates = ImportTaxRate.objects.filter(is_active=True).values("country_code", "country_name")
        return [
            {"country_code": r["country_code"], "country_name": r["country_name"]} for r in rates
        ]

    def _get_tax_rate(self, country_code: str) -> ImportTaxRate | None:
        """Get tax rate for a country, using cache if enabled."""
        # Normalize country code
        code = country_code.upper().strip()

        # Check cache first
        if self._use_cache and code in self._cache:
            return self._cache[code]

        # Query database
        from apps.search.models import ImportTaxRate

        try:
            tax_rate = ImportTaxRate.objects.get(
                country_code=code,
                is_active=True,
            )
            if self._use_cache:
                self._cache[code] = tax_rate
            return tax_rate
        except ImportTaxRate.DoesNotExist:
            return None

    def _convert_to_usd(self, amount: Decimal, currency: str) -> Decimal:
        """Convert amount to USD using exchange rate."""
        currency = currency.upper().strip()

        if currency == "USD":
            return amount

        rate = EXCHANGE_RATES_TO_USD.get(currency)
        if rate is None:
            # Unknown currency, assume 1:1 with USD
            logger.warning("Unknown currency, assuming 1:1 with USD", currency=currency)
            return amount

        return (amount * rate).quantize(Decimal("0.01"))

    def clear_cache(self) -> None:
        """Clear the tax rate cache."""
        self._cache.clear()
