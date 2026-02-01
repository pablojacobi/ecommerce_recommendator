"""Tests for tax calculator service."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.search.models import ImportTaxRate
from core.result import Success
from services.taxes import TaxBreakdown, TaxCalculationRequest, TaxCalculatorService


@pytest.fixture()
def tax_rate_chile(db: None) -> ImportTaxRate:
    """Create Chile tax rate."""
    return ImportTaxRate.objects.create(
        country_code="CL",
        country_name="Chile",
        vat_rate=Decimal("19.00"),
        customs_duty_rate=Decimal("6.00"),
        de_minimis_usd=Decimal("30.00"),
        currency_code="CLP",
        notes="Test rate for Chile",
        is_active=True,
    )


@pytest.fixture()
def tax_rate_us(db: None) -> ImportTaxRate:
    """Create US tax rate (high de minimis)."""
    return ImportTaxRate.objects.create(
        country_code="US",
        country_name="United States",
        vat_rate=Decimal("0.00"),
        customs_duty_rate=Decimal("5.00"),
        de_minimis_usd=Decimal("800.00"),
        currency_code="USD",
        notes="Test rate for US",
        is_active=True,
    )


@pytest.fixture()
def tax_rate_inactive(db: None) -> ImportTaxRate:
    """Create inactive tax rate."""
    return ImportTaxRate.objects.create(
        country_code="XX",
        country_name="Inactive Country",
        vat_rate=Decimal("50.00"),
        customs_duty_rate=Decimal("50.00"),
        de_minimis_usd=Decimal("0.00"),
        currency_code="XXX",
        is_active=False,
    )


@pytest.fixture()
def tax_service() -> TaxCalculatorService:
    """Create tax calculator service."""
    return TaxCalculatorService(use_cache=False)


class TestTaxCalculatorService:
    """Tests for TaxCalculatorService."""

    def test_init_with_cache(self) -> None:
        """Service should initialize with cache enabled by default."""
        service = TaxCalculatorService()
        assert service._use_cache is True
        assert service._cache == {}

    def test_init_without_cache(self) -> None:
        """Service should allow disabling cache."""
        service = TaxCalculatorService(use_cache=False)
        assert service._use_cache is False

    def test_calculate_with_taxes(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should calculate import taxes correctly."""
        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("20.00"),
            source_currency="USD",
            destination_country="CL",
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        breakdown = result.value

        assert breakdown.product_price_usd == Decimal("100.00")
        assert breakdown.shipping_cost_usd == Decimal("20.00")
        # Customs: 100 * 0.06 = 6.00
        assert breakdown.customs_duty == Decimal("6.00")
        # VAT: (100 + 20 + 6) * 0.19 = 23.94
        assert breakdown.vat == Decimal("23.94")
        assert breakdown.total_taxes == Decimal("29.94")
        # Total: 100 + 20 + 6 + 23.94 = 149.94
        assert breakdown.total_cost == Decimal("149.94")
        assert breakdown.destination_country == "CL"
        assert breakdown.destination_country_name == "Chile"
        assert breakdown.de_minimis_applied is False
        assert breakdown.is_estimated is True

    def test_calculate_de_minimis_applied(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should apply de minimis exemption for small values."""
        request = TaxCalculationRequest(
            product_price=Decimal("20.00"),
            shipping_cost=Decimal("5.00"),
            source_currency="USD",
            destination_country="CL",
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        breakdown = result.value

        # Under de minimis (30 USD), no taxes
        assert breakdown.customs_duty == Decimal("0")
        assert breakdown.vat == Decimal("0")
        assert breakdown.total_taxes == Decimal("0")
        assert breakdown.total_cost == Decimal("25.00")
        assert breakdown.de_minimis_applied is True

    def test_calculate_unknown_country(
        self,
        db: None,
        tax_service: TaxCalculatorService,
    ) -> None:
        """Should return no-tax breakdown for unknown country."""
        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("10.00"),
            source_currency="USD",
            destination_country="ZZ",
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        breakdown = result.value

        assert breakdown.customs_duty == Decimal("0")
        assert breakdown.vat == Decimal("0")
        assert breakdown.total_cost == Decimal("110.00")
        assert "No hay datos" in breakdown.notes

    def test_calculate_inactive_country(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_inactive: ImportTaxRate,
    ) -> None:
        """Should not use inactive tax rates."""
        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("10.00"),
            source_currency="USD",
            destination_country="XX",
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        # Should use no-tax fallback
        assert result.value.customs_duty == Decimal("0")

    def test_calculate_currency_conversion(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should convert non-USD currencies."""
        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("10.00"),
            source_currency="EUR",
            destination_country="CL",
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        # EUR is worth more than USD, so converted values should be higher
        assert result.value.product_price_usd > Decimal("100.00")

    def test_calculate_unknown_currency(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should assume 1:1 for unknown currencies."""
        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("10.00"),
            source_currency="XYZ",
            destination_country="CL",
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        # Should assume 1:1 conversion
        assert result.value.product_price_usd == Decimal("100.00")

    def test_calculate_case_insensitive_country(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should handle lowercase country codes."""
        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("0.00"),
            source_currency="USD",
            destination_country="cl",  # lowercase
        )

        result = tax_service.calculate(request)

        assert isinstance(result, Success)
        assert result.value.destination_country == "CL"


class TestTaxCalculatorServiceCache:
    """Tests for caching behavior."""

    def test_cache_stores_tax_rate(
        self,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should cache tax rates when enabled."""
        service = TaxCalculatorService(use_cache=True)

        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("0.00"),
            source_currency="USD",
            destination_country="CL",
        )

        # First call - should query DB
        service.calculate(request)
        assert "CL" in service._cache

        # Second call - should use cache
        service.calculate(request)
        # Cache should still have the rate
        assert service._cache["CL"].country_name == "Chile"

    def test_clear_cache(
        self,
        tax_rate_chile: ImportTaxRate,
    ) -> None:
        """Should clear cache when requested."""
        service = TaxCalculatorService(use_cache=True)

        request = TaxCalculationRequest(
            product_price=Decimal("100.00"),
            shipping_cost=Decimal("0.00"),
            source_currency="USD",
            destination_country="CL",
        )

        service.calculate(request)
        assert "CL" in service._cache

        service.clear_cache()
        assert service._cache == {}


class TestTaxCalculatorServiceBatch:
    """Tests for batch calculation."""

    def test_calculate_batch(
        self,
        tax_service: TaxCalculatorService,
        tax_rate_chile: ImportTaxRate,
        tax_rate_us: ImportTaxRate,
    ) -> None:
        """Should calculate taxes for multiple requests."""
        requests = [
            TaxCalculationRequest(
                product_price=Decimal("100.00"),
                shipping_cost=Decimal("10.00"),
                source_currency="USD",
                destination_country="CL",
            ),
            TaxCalculationRequest(
                product_price=Decimal("500.00"),
                shipping_cost=Decimal("50.00"),
                source_currency="USD",
                destination_country="US",
            ),
        ]

        results = tax_service.calculate_batch(requests)

        assert len(results) == 2
        assert all(isinstance(r, Success) for r in results)

        # Chile result
        assert isinstance(results[0], Success)
        chile = results[0].value
        assert chile.destination_country == "CL"
        assert chile.customs_duty > Decimal("0")

        # US result (under de minimis)
        assert isinstance(results[1], Success)
        us = results[1].value
        assert us.destination_country == "US"
        assert us.de_minimis_applied is True


class TestTaxCalculatorServiceCountries:
    """Tests for supported countries."""

    def test_get_supported_countries(
        self,
        tax_rate_chile: ImportTaxRate,
        tax_rate_us: ImportTaxRate,
        tax_rate_inactive: ImportTaxRate,
    ) -> None:
        """Should return only active countries."""
        service = TaxCalculatorService()

        countries = service.get_supported_countries()

        codes = [c["country_code"] for c in countries]
        assert "CL" in codes
        assert "US" in codes
        # Inactive should not be included
        assert "XX" not in codes


class TestTaxBreakdown:
    """Tests for TaxBreakdown dataclass."""

    def test_from_no_taxes(self) -> None:
        """Should create breakdown with zero taxes."""
        breakdown = TaxBreakdown.from_no_taxes(
            product_price_usd=Decimal("100.00"),
            shipping_cost_usd=Decimal("10.00"),
            destination_country="ZZ",
            destination_country_name="Unknown",
            notes="Test note",
        )

        assert breakdown.customs_duty == Decimal("0")
        assert breakdown.vat == Decimal("0")
        assert breakdown.total_taxes == Decimal("0")
        assert breakdown.total_cost == Decimal("110.00")
        assert breakdown.notes == "Test note"
        assert breakdown.is_estimated is True


class TestTaxCalculationRequest:
    """Tests for TaxCalculationRequest dataclass."""

    def test_create_request(self) -> None:
        """Should create request with all fields."""
        request = TaxCalculationRequest(
            product_price=Decimal("99.99"),
            shipping_cost=Decimal("9.99"),
            source_currency="EUR",
            destination_country="CL",
        )

        assert request.product_price == Decimal("99.99")
        assert request.shipping_cost == Decimal("9.99")
        assert request.source_currency == "EUR"
        assert request.destination_country == "CL"


class TestTaxCalculatorError:
    """Tests for TaxCalculatorError."""

    def test_error_message(self) -> None:
        """Should store error message."""
        from services.taxes.service import TaxCalculatorError

        error = TaxCalculatorError("Test error")
        assert error.message == "Test error"
        assert str(error) == "Test error"
