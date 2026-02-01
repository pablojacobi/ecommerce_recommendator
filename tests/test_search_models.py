"""Tests for search app models."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.search.models import ImportTaxRate, Marketplace


@pytest.mark.django_db
class TestImportTaxRateModel:
    """Tests for ImportTaxRate model."""

    @pytest.fixture()
    def chile_tax(self) -> ImportTaxRate:
        """Create Chile tax rate fixture."""
        return ImportTaxRate.objects.create(
            country_code="CL",
            country_name="Chile",
            vat_rate=Decimal("19.00"),
            customs_duty_rate=Decimal("6.00"),
            de_minimis_usd=Decimal("30.00"),
            currency_code="CLP",
        )

    def test_create_tax_rate(self) -> None:
        """ImportTaxRate can be created."""
        tax = ImportTaxRate.objects.create(
            country_code="US",
            country_name="United States",
            vat_rate=Decimal("0.00"),
            customs_duty_rate=Decimal("5.00"),
            de_minimis_usd=Decimal("800.00"),
        )

        assert tax.country_code == "US"
        assert tax.is_active is True

    def test_str(self, chile_tax: ImportTaxRate) -> None:
        """__str__ returns country name and code."""
        assert str(chile_tax) == "Chile (CL)"

    def test_calculate_import_cost_below_de_minimis(self, chile_tax: ImportTaxRate) -> None:
        """No taxes applied when below de minimis threshold."""
        result = chile_tax.calculate_import_cost(
            product_price_usd=Decimal("20.00"),
            shipping_cost_usd=Decimal("5.00"),
        )

        assert result["customs_duty"] == Decimal("0")
        assert result["vat"] == Decimal("0")
        assert result["total"] == Decimal("25.00")

    def test_calculate_import_cost_above_de_minimis(self, chile_tax: ImportTaxRate) -> None:
        """Taxes applied when above de minimis threshold."""
        result = chile_tax.calculate_import_cost(
            product_price_usd=Decimal("100.00"),
            shipping_cost_usd=Decimal("10.00"),
        )

        # Customs duty: 100 * 6% = 6.00
        assert result["customs_duty"] == Decimal("6.00")
        # VAT: (100 + 10 + 6) * 19% = 22.04
        assert result["vat"] == Decimal("22.04")
        # Total: 100 + 10 + 6 + 22.04 = 138.04
        assert result["total"] == Decimal("138.04")

    def test_calculate_import_cost_no_shipping(self, chile_tax: ImportTaxRate) -> None:
        """Import cost calculation works without shipping."""
        result = chile_tax.calculate_import_cost(
            product_price_usd=Decimal("50.00"),
        )

        assert result["shipping_cost"] == Decimal("0")
        assert result["product_price"] == Decimal("50.00")


@pytest.mark.django_db
class TestMarketplaceModel:
    """Tests for Marketplace model."""

    @pytest.fixture()
    def ebay_us(self) -> Marketplace:
        """Create eBay US marketplace fixture."""
        return Marketplace.objects.create(
            code="EBAY_US",
            name="eBay USA",
            provider=Marketplace.Provider.EBAY,
            country_code="US",
            country_name="United States",
            api_site_id="EBAY_US",
            currency_code="USD",
        )

    @pytest.fixture()
    def meli_chile(self) -> Marketplace:
        """Create MercadoLibre Chile marketplace fixture."""
        return Marketplace.objects.create(
            code="MLC",
            name="MercadoLibre Chile",
            provider=Marketplace.Provider.MERCADOLIBRE,
            country_code="CL",
            country_name="Chile",
            api_site_id="MLC",
            currency_code="CLP",
        )

    def test_create_marketplace(self) -> None:
        """Marketplace can be created."""
        marketplace = Marketplace.objects.create(
            code="TEST",
            name="Test Marketplace",
            provider=Marketplace.Provider.EBAY,
            country_code="US",
            country_name="United States",
        )

        assert marketplace.code == "TEST"
        assert marketplace.is_active is True

    def test_str(self, ebay_us: Marketplace) -> None:
        """__str__ returns marketplace name."""
        assert str(ebay_us) == "eBay USA"

    def test_is_ebay(self, ebay_us: Marketplace, meli_chile: Marketplace) -> None:
        """is_ebay returns True for eBay marketplaces."""
        assert ebay_us.is_ebay is True
        assert ebay_us.is_mercadolibre is False

    def test_is_mercadolibre(self, ebay_us: Marketplace, meli_chile: Marketplace) -> None:
        """is_mercadolibre returns True for MercadoLibre marketplaces."""
        assert meli_chile.is_mercadolibre is True
        assert meli_chile.is_ebay is False

    def test_marketplace_ordering(self) -> None:
        """Marketplaces are ordered by display_order then name."""
        m2 = Marketplace.objects.create(
            code="M2",
            name="Beta",
            provider=Marketplace.Provider.EBAY,
            country_code="US",
            country_name="US",
            display_order=2,
        )
        m1 = Marketplace.objects.create(
            code="M1",
            name="Alpha",
            provider=Marketplace.Provider.EBAY,
            country_code="US",
            country_name="US",
            display_order=1,
        )

        marketplaces = list(Marketplace.objects.all())
        assert marketplaces[0] == m1
        assert marketplaces[1] == m2
