"""Types for tax calculation service."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class TaxCalculationRequest:
    """
    Request for tax calculation.

    Attributes:
        product_price: Product price in original currency.
        shipping_cost: Shipping cost in original currency.
        source_currency: Currency of the product/shipping prices.
        destination_country: ISO country code of destination.
    """

    product_price: Decimal
    shipping_cost: Decimal
    source_currency: str
    destination_country: str


@dataclass(frozen=True, slots=True)
class TaxBreakdown:
    """
    Breakdown of import taxes and costs.

    All values are in USD for standardization.

    Attributes:
        product_price_usd: Product price in USD.
        shipping_cost_usd: Shipping cost in USD.
        customs_duty: Customs/import duty.
        vat: VAT/IVA tax.
        total_taxes: Total of customs_duty + vat.
        total_cost: Grand total including all costs and taxes.
        destination_country: Country code where taxes apply.
        destination_country_name: Country name for display.
        vat_rate: VAT rate applied (percentage).
        customs_duty_rate: Customs duty rate applied (percentage).
        de_minimis_applied: Whether de minimis exemption was applied.
        is_estimated: Whether these are estimated values.
        notes: Additional notes about the calculation.
    """

    product_price_usd: Decimal
    shipping_cost_usd: Decimal
    customs_duty: Decimal
    vat: Decimal
    total_taxes: Decimal
    total_cost: Decimal
    destination_country: str
    destination_country_name: str
    vat_rate: Decimal
    customs_duty_rate: Decimal
    de_minimis_applied: bool = False
    is_estimated: bool = True
    notes: str = ""

    @classmethod
    def from_no_taxes(
        cls,
        product_price_usd: Decimal,
        shipping_cost_usd: Decimal,
        destination_country: str,
        destination_country_name: str,
        notes: str = "",
    ) -> TaxBreakdown:
        """Create a breakdown with no taxes (e.g., unknown country)."""
        total = product_price_usd + shipping_cost_usd
        return cls(
            product_price_usd=product_price_usd,
            shipping_cost_usd=shipping_cost_usd,
            customs_duty=Decimal("0"),
            vat=Decimal("0"),
            total_taxes=Decimal("0"),
            total_cost=total,
            destination_country=destination_country,
            destination_country_name=destination_country_name,
            vat_rate=Decimal("0"),
            customs_duty_rate=Decimal("0"),
            de_minimis_applied=False,
            is_estimated=True,
            notes=notes,
        )
