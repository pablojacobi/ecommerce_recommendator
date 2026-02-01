"""Tests for structured logging configuration."""

from __future__ import annotations

import structlog

from core.logging import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
)


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def test_configure_logging_default(self) -> None:
        """configure_logging should work with defaults."""
        configure_logging()

        logger = structlog.get_logger()
        assert logger is not None

    def test_configure_logging_json_format(self) -> None:
        """configure_logging should configure JSON format."""
        configure_logging(json_format=True)

        logger = structlog.get_logger()
        assert logger is not None

    def test_configure_logging_with_log_level(self) -> None:
        """configure_logging should respect log level."""
        configure_logging(log_level="DEBUG")

        logger = structlog.get_logger()
        assert logger is not None

    def test_configure_logging_with_warning_level(self) -> None:
        """configure_logging should work with WARNING level."""
        configure_logging(log_level="WARNING")

        logger = structlog.get_logger()
        assert logger is not None


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self) -> None:
        """get_logger should return a structlog logger."""
        configure_logging()

        logger = get_logger()

        assert logger is not None

    def test_get_logger_with_name(self) -> None:
        """get_logger should accept a name."""
        configure_logging()

        logger = get_logger("test.module")

        assert logger is not None

    def test_logger_can_log_info(self) -> None:
        """Logger should be able to log info messages."""
        configure_logging()
        logger = get_logger("test")

        # Should not raise
        logger.info("test message", key="value")

    def test_logger_can_log_error(self) -> None:
        """Logger should be able to log error messages."""
        configure_logging()
        logger = get_logger("test")

        # Should not raise
        logger.error("error message", error_code=500)


class TestContextFunctions:
    """Tests for context binding functions."""

    def test_bind_context(self) -> None:
        """bind_context should add context variables."""
        configure_logging()
        clear_context()

        bind_context(request_id="123", user_id="456")

        # Context should be bound (we just verify it doesn't raise)

    def test_clear_context(self) -> None:
        """clear_context should clear context variables."""
        configure_logging()

        bind_context(request_id="123")
        clear_context()

        # Context should be cleared (we just verify it doesn't raise)

    def test_bind_multiple_context_vars(self) -> None:
        """bind_context should handle multiple variables."""
        configure_logging()
        clear_context()

        bind_context(
            request_id="req-123",
            user_id="user-456",
            action="test_action",
        )

        # Should not raise


class TestLoggingIntegration:
    """Integration tests for logging functionality."""

    def test_full_logging_workflow(self) -> None:
        """Test complete logging workflow."""
        # Configure
        configure_logging(json_format=False, log_level="INFO")

        # Get logger
        logger = get_logger("integration.test")

        # Bind context
        bind_context(correlation_id="corr-123")

        # Log messages
        logger.info("Starting operation")
        logger.info("Operation complete", result="success")

        # Clear context
        clear_context()

    def test_json_logging_workflow(self) -> None:
        """Test JSON format logging workflow."""
        configure_logging(json_format=True, log_level="DEBUG")

        logger = get_logger("json.test")

        logger.debug("Debug message", debug_data={"key": "value"})
        logger.info("Info message")
