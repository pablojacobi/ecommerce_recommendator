"""Tests for Pydantic Settings configuration."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from pydantic import SecretStr

if TYPE_CHECKING:
    import pytest

from core.config import (
    DatabaseSettings,
    EbaySettings,
    GeminiSettings,
    MercadoLibreSettings,
    RedisSettings,
    SentrySettings,
    Settings,
    get_settings,
)


class TestDatabaseSettings:
    """Tests for DatabaseSettings."""

    def test_default_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DatabaseSettings should have sensible defaults."""
        # Clear any environment variables that could affect defaults
        for key in list(os.environ.keys()):
            if key.startswith("DB_") or key == "DATABASE_URL":
                monkeypatch.delenv(key, raising=False)

        settings = DatabaseSettings()

        assert settings.name == "ecommerce_recommendator"
        assert settings.user == "postgres"
        assert settings.host == "localhost"
        assert settings.port == 5432
        assert settings.url is None

    def test_connection_url_from_individual_params(self) -> None:
        """connection_url should build URL from individual parameters."""
        settings = DatabaseSettings(
            name="testdb",
            user="testuser",
            password=SecretStr("testpass"),
            host="testhost",
            port=5433,
        )

        expected = "postgresql://testuser:testpass@testhost:5433/testdb"
        assert settings.connection_url == expected

    def test_connection_url_from_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """connection_url should use DATABASE_URL when provided."""
        database_url = "postgresql://user:pass@db.example.com:5432/mydb"
        monkeypatch.setenv("DATABASE_URL", database_url)

        settings = DatabaseSettings()

        assert settings.connection_url == database_url

    def test_database_url_takes_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DATABASE_URL should take precedence over individual params."""
        database_url = "postgresql://urluser:urlpass@urlhost:5432/urldb"
        monkeypatch.setenv("DATABASE_URL", database_url)
        monkeypatch.setenv("DB_NAME", "paramdb")
        monkeypatch.setenv("DB_USER", "paramuser")

        settings = DatabaseSettings()

        # Should use DATABASE_URL, not individual params
        assert settings.connection_url == database_url
        assert "urldb" in settings.connection_url
        assert "paramdb" not in settings.connection_url

    def test_safe_url_redacts_password_from_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """safe_url should redact password from DATABASE_URL."""
        database_url = "postgresql://user:secretpass@db.example.com:5432/mydb"
        monkeypatch.setenv("DATABASE_URL", database_url)

        settings = DatabaseSettings()

        assert "secretpass" not in settings.safe_url
        assert "***" in settings.safe_url
        assert "user" in settings.safe_url
        assert "db.example.com" in settings.safe_url

    def test_safe_url_from_individual_params(self) -> None:
        """safe_url should not include password when built from params."""
        settings = DatabaseSettings(
            name="testdb",
            user="testuser",
            password=SecretStr("secretpass"),
            host="testhost",
            port=5433,
        )

        assert "secretpass" not in settings.safe_url
        assert settings.safe_url == "postgresql://testuser@testhost:5433/testdb"

    def test_url_property(self) -> None:
        """url property should build correct database URL."""
        settings = DatabaseSettings(
            name="testdb",
            user="testuser",
            host="testhost",
            port=5433,
        )

        # url is now the raw DATABASE_URL or None
        assert settings.url is None

    def test_password_is_secret(self) -> None:
        """Password should be stored as SecretStr."""
        settings = DatabaseSettings(password=SecretStr("secret123"))

        assert settings.password.get_secret_value() == "secret123"


class TestRedisSettings:
    """Tests for RedisSettings."""

    def test_default_url(self) -> None:
        """RedisSettings should have default localhost URL."""
        settings = RedisSettings()

        assert settings.url == "redis://localhost:6379/0"


class TestMercadoLibreSettings:
    """Tests for MercadoLibreSettings."""

    def test_is_configured_false_when_empty(self) -> None:
        """is_configured should return False when credentials are empty."""
        settings = MercadoLibreSettings()

        assert settings.is_configured is False

    def test_is_configured_true_when_set(self) -> None:
        """is_configured should return True when all credentials are set."""
        settings = MercadoLibreSettings(
            app_id="12345",
            client_secret=SecretStr("secret"),
        )

        assert settings.is_configured is True

    def test_is_configured_false_with_only_app_id(self) -> None:
        """is_configured should return False with only app_id."""
        settings = MercadoLibreSettings(app_id="12345")

        assert settings.is_configured is False


class TestEbaySettings:
    """Tests for EbaySettings."""

    def test_is_configured_false_when_empty(self) -> None:
        """is_configured should return False when credentials are empty."""
        settings = EbaySettings()

        assert settings.is_configured is False

    def test_is_configured_true_when_all_set(self) -> None:
        """is_configured should return True when all credentials are set."""
        settings = EbaySettings(
            app_id="app123",
            dev_id="dev123",
            cert_id=SecretStr("cert123"),
        )

        assert settings.is_configured is True

    def test_is_configured_false_with_partial_creds(self) -> None:
        """is_configured should return False with partial credentials."""
        settings = EbaySettings(app_id="app123", dev_id="dev123")

        assert settings.is_configured is False


class TestGeminiSettings:
    """Tests for GeminiSettings."""

    def test_default_model(self) -> None:
        """GeminiSettings should default to gemini-2.0-flash."""
        settings = GeminiSettings()

        assert settings.model == "gemini-2.0-flash"

    def test_is_configured_false_when_empty(self) -> None:
        """is_configured should return False when API key is empty."""
        settings = GeminiSettings()

        assert settings.is_configured is False

    def test_is_configured_true_when_set(self) -> None:
        """is_configured should return True when API key is set."""
        settings = GeminiSettings(api_key=SecretStr("api-key-123"))

        assert settings.is_configured is True


class TestSentrySettings:
    """Tests for SentrySettings."""

    def test_default_values(self) -> None:
        """SentrySettings should have sensible defaults."""
        settings = SentrySettings()

        assert settings.dsn == ""
        assert settings.environment == "development"
        assert settings.traces_sample_rate == 0.1

    def test_is_configured_false_when_no_dsn(self) -> None:
        """is_configured should return False when DSN is empty."""
        settings = SentrySettings()

        assert settings.is_configured is False

    def test_is_configured_true_when_dsn_set(self) -> None:
        """is_configured should return True when DSN is set."""
        settings = SentrySettings(dsn="https://sentry.io/123")

        assert settings.is_configured is True


class TestSettings:
    """Tests for main Settings class."""

    def test_default_environment(self) -> None:
        """Settings should default to development environment."""
        settings = Settings()

        assert settings.environment == "development"
        assert settings.debug is False

    def test_environment_properties(self) -> None:
        """Environment properties should work correctly."""
        dev_settings = Settings(environment="development")
        prod_settings = Settings(environment="production")
        test_settings = Settings(environment="test")

        assert dev_settings.is_development is True
        assert dev_settings.is_production is False
        assert dev_settings.is_test is False

        assert prod_settings.is_production is True
        assert prod_settings.is_development is False

        assert test_settings.is_test is True

    def test_parse_allowed_hosts_from_string(self) -> None:
        """allowed_hosts should parse comma-separated string."""
        settings = Settings(allowed_hosts="localhost,example.com,api.example.com")

        assert settings.allowed_hosts == ["localhost", "example.com", "api.example.com"]

    def test_parse_allowed_hosts_handles_whitespace(self) -> None:
        """allowed_hosts should handle whitespace in string."""
        settings = Settings(allowed_hosts="localhost , example.com , ")

        assert settings.allowed_hosts == ["localhost", "example.com"]

    def test_parse_allowed_hosts_from_list(self) -> None:
        """allowed_hosts should accept list directly."""
        hosts = ["localhost", "example.com"]
        settings = Settings(allowed_hosts=hosts)

        assert settings.allowed_hosts == hosts

    def test_nested_settings(self) -> None:
        """Settings should contain nested settings objects."""
        settings = Settings()

        assert isinstance(settings.database, DatabaseSettings)
        assert isinstance(settings.redis, RedisSettings)
        assert isinstance(settings.mercadolibre, MercadoLibreSettings)
        assert isinstance(settings.ebay, EbaySettings)
        assert isinstance(settings.gemini, GeminiSettings)
        assert isinstance(settings.sentry, SentrySettings)


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_returns_settings(self) -> None:
        """get_settings should return Settings instance."""
        # Clear cache for test
        get_settings.cache_clear()

        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_get_settings_is_cached(self) -> None:
        """get_settings should return cached instance."""
        get_settings.cache_clear()

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2
