"""Tests for marketplace error types."""

from __future__ import annotations

from services.marketplaces.errors import (
    AuthenticationError,
    ErrorCode,
    MarketplaceError,
    NetworkError,
    NotFoundError,
    ParseError,
    RateLimitError,
)


class TestErrorCode:
    """Tests for ErrorCode enum."""

    def test_error_codes_exist(self) -> None:
        """ErrorCode should have all expected values."""
        assert ErrorCode.UNKNOWN.value == "unknown"
        assert ErrorCode.RATE_LIMIT.value == "rate_limit"
        assert ErrorCode.AUTHENTICATION.value == "authentication"
        assert ErrorCode.NETWORK.value == "network"
        assert ErrorCode.PARSE.value == "parse"
        assert ErrorCode.NOT_FOUND.value == "not_found"
        assert ErrorCode.INVALID_REQUEST.value == "invalid_request"
        assert ErrorCode.SERVICE_UNAVAILABLE.value == "service_unavailable"


class TestMarketplaceError:
    """Tests for MarketplaceError dataclass."""

    def test_create_error(self) -> None:
        """MarketplaceError can be created with required fields."""
        error = MarketplaceError(
            code=ErrorCode.NETWORK,
            message="Connection failed",
            marketplace_code="EBAY_US",
        )

        assert error.code == ErrorCode.NETWORK
        assert error.message == "Connection failed"
        assert error.marketplace_code == "EBAY_US"
        assert error.details is None
        assert error.retry_after is None

    def test_create_error_with_details(self) -> None:
        """MarketplaceError can include details."""
        error = MarketplaceError(
            code=ErrorCode.RATE_LIMIT,
            message="Too many requests",
            marketplace_code="MLC",
            details="Retry after 60 seconds",
            retry_after=60,
        )

        assert error.details == "Retry after 60 seconds"
        assert error.retry_after == 60

    def test_str_representation(self) -> None:
        """MarketplaceError __str__ should be readable."""
        error = MarketplaceError(
            code=ErrorCode.AUTHENTICATION,
            message="Invalid API key",
            marketplace_code="EBAY_US",
        )

        assert str(error) == "[EBAY_US] authentication: Invalid API key"

    def test_is_retryable_true(self) -> None:
        """is_retryable should return True for retryable errors."""
        rate_limit = MarketplaceError(
            code=ErrorCode.RATE_LIMIT,
            message="test",
            marketplace_code="test",
        )
        network = MarketplaceError(
            code=ErrorCode.NETWORK,
            message="test",
            marketplace_code="test",
        )
        unavailable = MarketplaceError(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            message="test",
            marketplace_code="test",
        )

        assert rate_limit.is_retryable is True
        assert network.is_retryable is True
        assert unavailable.is_retryable is True

    def test_is_retryable_false(self) -> None:
        """is_retryable should return False for non-retryable errors."""
        auth = MarketplaceError(
            code=ErrorCode.AUTHENTICATION,
            message="test",
            marketplace_code="test",
        )
        parse = MarketplaceError(
            code=ErrorCode.PARSE,
            message="test",
            marketplace_code="test",
        )
        not_found = MarketplaceError(
            code=ErrorCode.NOT_FOUND,
            message="test",
            marketplace_code="test",
        )

        assert auth.is_retryable is False
        assert parse.is_retryable is False
        assert not_found.is_retryable is False


class TestErrorFactoryFunctions:
    """Tests for error factory functions."""

    def test_rate_limit_error(self) -> None:
        """RateLimitError should create correct error."""
        error = RateLimitError("EBAY_US", retry_after=30)

        assert error.code == ErrorCode.RATE_LIMIT
        assert error.marketplace_code == "EBAY_US"
        assert error.message == "Rate limit exceeded"
        assert error.retry_after == 30

    def test_rate_limit_error_custom_message(self) -> None:
        """RateLimitError should accept custom message."""
        error = RateLimitError("MLC", message="API quota exhausted")

        assert error.message == "API quota exhausted"

    def test_authentication_error(self) -> None:
        """AuthenticationError should create correct error."""
        error = AuthenticationError("EBAY_US", details="Token expired")

        assert error.code == ErrorCode.AUTHENTICATION
        assert error.marketplace_code == "EBAY_US"
        assert error.message == "Authentication failed"
        assert error.details == "Token expired"

    def test_network_error(self) -> None:
        """NetworkError should create correct error."""
        error = NetworkError("MLC", message="Connection timeout")

        assert error.code == ErrorCode.NETWORK
        assert error.marketplace_code == "MLC"
        assert error.message == "Connection timeout"

    def test_parse_error(self) -> None:
        """ParseError should create correct error."""
        error = ParseError("EBAY_US", details="Invalid JSON")

        assert error.code == ErrorCode.PARSE
        assert error.marketplace_code == "EBAY_US"
        assert error.message == "Failed to parse response"
        assert error.details == "Invalid JSON"

    def test_not_found_error(self) -> None:
        """NotFoundError should create correct error."""
        error = NotFoundError("MLC", message="Product not found")

        assert error.code == ErrorCode.NOT_FOUND
        assert error.marketplace_code == "MLC"
        assert error.message == "Product not found"
