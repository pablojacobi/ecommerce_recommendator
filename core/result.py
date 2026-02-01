"""
Result pattern for explicit error handling.

This module provides a Result type that makes error handling explicit
by returning either a Success or Failure value instead of raising exceptions.

Example:
    >>> def divide(a: int, b: int) -> Result[float, str]:
    ...     if b == 0:
    ...         return Failure("Division by zero")
    ...     return Success(a / b)
    ...
    >>> result = divide(10, 2)
    >>> if result.is_success():
    ...     print(f"Result: {result.unwrap()}")
    ... else:
    ...     print(f"Error: {result.error}")
    Result: 5.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Never

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True, slots=True)
class Success[T]:
    """
    Represents a successful result containing a value.

    Attributes:
        value: The success value.
    """

    value: T

    def is_success(self) -> bool:
        """Return True if this is a Success."""
        return True

    def is_failure(self) -> bool:
        """Return False if this is a Success."""
        return False

    def unwrap(self) -> T:
        """
        Return the success value.

        Returns:
            The contained success value.
        """
        return self.value

    def unwrap_or(self, _default: T) -> T:
        """
        Return the success value (ignores default).

        Args:
            _default: Default value (ignored for Success).

        Returns:
            The contained success value.
        """
        return self.value

    def map[U](self, func: Callable[[T], U]) -> Success[U]:
        """
        Apply a function to the success value.

        Args:
            func: Function to apply to the value.

        Returns:
            New Success with the mapped value.
        """
        return Success(func(self.value))

    def map_error[E, U](self, _func: Callable[[E], U]) -> Success[T]:
        """
        Do nothing for Success (error mapping doesn't apply).

        Args:
            _func: Function to apply to error (not used).

        Returns:
            Self unchanged.
        """
        return self


@dataclass(frozen=True, slots=True)
class Failure[E]:
    """
    Represents a failed result containing an error.

    Attributes:
        error: The error value.
    """

    error: E

    def is_success(self) -> bool:
        """Return False if this is a Failure."""
        return False

    def is_failure(self) -> bool:
        """Return True if this is a Failure."""
        return True

    def unwrap(self) -> Never:
        """
        Raise an error since this is a Failure.

        Raises:
            ValueError: Always, since Failure has no success value.
        """
        raise ValueError(f"Cannot unwrap Failure: {self.error}")

    def unwrap_or[T](self, default: T) -> T:
        """
        Return the default value since this is a Failure.

        Args:
            default: Default value to return.

        Returns:
            The provided default value.
        """
        return default

    def map[T, U](self, _func: Callable[[T], U]) -> Failure[E]:
        """
        Do nothing for Failure (value mapping doesn't apply).

        Args:
            _func: Function to apply to value (not used).

        Returns:
            Self unchanged.
        """
        return self

    def map_error[U](self, func: Callable[[E], U]) -> Failure[U]:
        """
        Apply a function to the error value.

        Args:
            func: Function to apply to the error.

        Returns:
            New Failure with the mapped error.
        """
        return Failure(func(self.error))


# Type alias for Result
type Result[T, E] = Success[T] | Failure[E]


def success[T](value: T) -> Success[T]:
    """
    Create a Success result.

    Args:
        value: The success value.

    Returns:
        A Success containing the value.
    """
    return Success(value)


def failure[E](error: E) -> Failure[E]:
    """
    Create a Failure result.

    Args:
        error: The error value.

    Returns:
        A Failure containing the error.
    """
    return Failure(error)
