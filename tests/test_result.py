"""Tests for Result pattern implementation."""

from __future__ import annotations

import pytest

from core.result import Failure, Success, failure, success


class TestSuccess:
    """Tests for Success class."""

    def test_is_success_returns_true(self) -> None:
        """Success.is_success() should return True."""
        result = Success(42)

        assert result.is_success() is True

    def test_is_failure_returns_false(self) -> None:
        """Success.is_failure() should return False."""
        result = Success(42)

        assert result.is_failure() is False

    def test_unwrap_returns_value(self) -> None:
        """Success.unwrap() should return the contained value."""
        result = Success("hello")

        assert result.unwrap() == "hello"

    def test_unwrap_or_returns_value(self) -> None:
        """Success.unwrap_or() should return value, ignoring default."""
        result = Success(100)

        assert result.unwrap_or(0) == 100

    def test_map_transforms_value(self) -> None:
        """Success.map() should transform the contained value."""
        result = Success(5)

        mapped = result.map(lambda x: x * 2)

        assert mapped.unwrap() == 10

    def test_map_error_returns_self(self) -> None:
        """Success.map_error() should return self unchanged."""
        result: Success[int] = Success(42)

        mapped = result.map_error(lambda e: str(e))

        assert mapped is result

    def test_value_attribute(self) -> None:
        """Success.value should contain the value."""
        result = Success({"key": "value"})

        assert result.value == {"key": "value"}


class TestFailure:
    """Tests for Failure class."""

    def test_is_success_returns_false(self) -> None:
        """Failure.is_success() should return False."""
        result = Failure("error")

        assert result.is_success() is False

    def test_is_failure_returns_true(self) -> None:
        """Failure.is_failure() should return True."""
        result = Failure("error")

        assert result.is_failure() is True

    def test_unwrap_raises_value_error(self) -> None:
        """Failure.unwrap() should raise ValueError."""
        result = Failure("something went wrong")

        with pytest.raises(ValueError, match="Cannot unwrap Failure"):
            result.unwrap()

    def test_unwrap_or_returns_default(self) -> None:
        """Failure.unwrap_or() should return the default value."""
        result: Failure[str] = Failure("error")

        assert result.unwrap_or(42) == 42

    def test_map_returns_self(self) -> None:
        """Failure.map() should return self unchanged."""
        result: Failure[str] = Failure("error")

        mapped = result.map(lambda x: str(x))

        assert mapped is result

    def test_map_error_transforms_error(self) -> None:
        """Failure.map_error() should transform the error."""
        result = Failure(404)

        mapped = result.map_error(lambda e: f"Error code: {e}")

        assert mapped.error == "Error code: 404"

    def test_error_attribute(self) -> None:
        """Failure.error should contain the error."""
        result = Failure(ValueError("invalid"))

        assert isinstance(result.error, ValueError)


class TestSuccessFunction:
    """Tests for success() helper function."""

    def test_creates_success(self) -> None:
        """success() should create a Success instance."""
        result = success(42)

        assert isinstance(result, Success)
        assert result.value == 42


class TestFailureFunction:
    """Tests for failure() helper function."""

    def test_creates_failure(self) -> None:
        """failure() should create a Failure instance."""
        result = failure("error message")

        assert isinstance(result, Failure)
        assert result.error == "error message"


class TestResultUsagePatterns:
    """Tests demonstrating common Result usage patterns."""

    def test_pattern_matching_with_is_success(self) -> None:
        """Demonstrate pattern matching with is_success()."""

        def divide(a: int, b: int) -> Success[float] | Failure[str]:
            if b == 0:
                return Failure("Division by zero")
            return Success(a / b)

        result = divide(10, 2)

        if result.is_success():
            assert result.unwrap() == 5.0

    def test_chained_map_operations(self) -> None:
        """Demonstrate chaining map operations."""
        result = Success(5)

        final = result.map(lambda x: x * 2).map(lambda x: x + 1)

        assert final.unwrap() == 11

    def test_error_propagation_through_map(self) -> None:
        """Demonstrate error propagation through map."""
        result: Failure[str] = Failure("initial error")

        # Map should not transform failure
        mapped = result.map(lambda x: str(x))

        assert mapped.is_failure()
        assert mapped.error == "initial error"
