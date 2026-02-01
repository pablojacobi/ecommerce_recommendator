"""Error types for marketplace adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """Error codes for marketplace errors."""

    UNKNOWN = "unknown"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    PARSE = "parse"
    NOT_FOUND = "not_found"
    INVALID_REQUEST = "invalid_request"
    SERVICE_UNAVAILABLE = "service_unavailable"


@dataclass(frozen=True, slots=True)
class MarketplaceError:
    """
    Base error type for marketplace operations.

    Attributes:
        code: Error code identifying the type of error.
        message: Human-readable error message.
        marketplace_code: Code of the marketplace that produced the error.
        details: Additional error details (optional).
        retry_after: Seconds to wait before retrying (for rate limits).
    """

    code: ErrorCode
    message: str
    marketplace_code: str
    details: str | None = None
    retry_after: int | None = None

    def __str__(self) -> str:
        """Return string representation of the error."""
        return f"[{self.marketplace_code}] {self.code.value}: {self.message}"

    @property
    def is_retryable(self) -> bool:
        """Check if this error type is retryable."""
        return self.code in {
            ErrorCode.RATE_LIMIT,
            ErrorCode.NETWORK,
            ErrorCode.SERVICE_UNAVAILABLE,
        }


def RateLimitError(
    marketplace_code: str,
    message: str = "Rate limit exceeded",
    retry_after: int | None = None,
) -> MarketplaceError:
    """Create a rate limit error."""
    return MarketplaceError(
        code=ErrorCode.RATE_LIMIT,
        message=message,
        marketplace_code=marketplace_code,
        retry_after=retry_after,
    )


def AuthenticationError(
    marketplace_code: str,
    message: str = "Authentication failed",
    details: str | None = None,
) -> MarketplaceError:
    """Create an authentication error."""
    return MarketplaceError(
        code=ErrorCode.AUTHENTICATION,
        message=message,
        marketplace_code=marketplace_code,
        details=details,
    )


def NetworkError(
    marketplace_code: str,
    message: str = "Network error",
    details: str | None = None,
) -> MarketplaceError:
    """Create a network error."""
    return MarketplaceError(
        code=ErrorCode.NETWORK,
        message=message,
        marketplace_code=marketplace_code,
        details=details,
    )


def ParseError(
    marketplace_code: str,
    message: str = "Failed to parse response",
    details: str | None = None,
) -> MarketplaceError:
    """Create a parse error."""
    return MarketplaceError(
        code=ErrorCode.PARSE,
        message=message,
        marketplace_code=marketplace_code,
        details=details,
    )


def NotFoundError(
    marketplace_code: str,
    message: str = "Resource not found",
    details: str | None = None,
) -> MarketplaceError:
    """Create a not found error."""
    return MarketplaceError(
        code=ErrorCode.NOT_FOUND,
        message=message,
        marketplace_code=marketplace_code,
        details=details,
    )
