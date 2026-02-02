"""
Application configuration using Pydantic Settings.

This module provides typed and validated settings for the application,
with support for environment variables and .env files.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database connection settings."""

    model_config = SettingsConfigDict(env_prefix="DB_")

    # Support both DATABASE_URL and individual parameters
    url: str | None = Field(
        default=None,
        alias="DATABASE_URL",
        description="Full database URL (takes precedence over individual params)",
    )

    # Individual parameters (fallback if DATABASE_URL not provided)
    name: str = Field(default="ecommerce_recommendator", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: SecretStr = Field(default=SecretStr("postgres"), description="Database password")
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port", ge=1, le=65535)

    @property
    def connection_url(self) -> str:
        """
        Get database connection URL.

        If DATABASE_URL is set, use it directly.
        Otherwise, build from individual parameters.
        """
        if self.url:
            return self.url
        return (
            f"postgresql://{self.user}:{self.password.get_secret_value()}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def safe_url(self) -> str:
        """Get database URL without password for logging."""
        if self.url:
            # Parse and redact password from URL
            parsed = urlparse(self.url)
            if parsed.password:
                return self.url.replace(f":{parsed.password}@", ":***@")
            return self.url
        return f"postgresql://{self.user}@{self.host}:{self.port}/{self.name}"


class RedisSettings(BaseSettings):
    """Redis connection settings."""

    model_config = SettingsConfigDict(env_prefix="REDIS_")

    url: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")


class MercadoLibreSettings(BaseSettings):
    """MercadoLibre API settings."""

    model_config = SettingsConfigDict(env_prefix="MELI_")

    app_id: str = Field(default="", description="MercadoLibre App ID")
    client_secret: SecretStr = Field(
        default=SecretStr(""), description="MercadoLibre Client Secret"
    )

    @property
    def is_configured(self) -> bool:
        """Check if MercadoLibre credentials are configured."""
        return bool(self.app_id and self.client_secret.get_secret_value())


class EbaySettings(BaseSettings):
    """eBay API settings."""

    model_config = SettingsConfigDict(env_prefix="EBAY_")

    app_id: str = Field(default="", description="eBay App ID")
    dev_id: str = Field(default="", description="eBay Dev ID")
    cert_id: SecretStr = Field(default=SecretStr(""), description="eBay Cert ID")

    @property
    def is_configured(self) -> bool:
        """Check if eBay credentials are configured."""
        return bool(self.app_id and self.dev_id and self.cert_id.get_secret_value())


class GeminiSettings(BaseSettings):
    """Google Gemini API settings."""

    model_config = SettingsConfigDict(env_prefix="GEMINI_")

    api_key: SecretStr = Field(default=SecretStr(""), description="Gemini API Key")
    model: str = Field(default="gemini-2.0-flash", description="Gemini model to use")

    @property
    def is_configured(self) -> bool:
        """Check if Gemini API key is configured."""
        return bool(self.api_key.get_secret_value())


class Settings(BaseSettings):
    """
    Main application settings.

    Aggregates all configuration sections and provides environment-specific
    settings loading.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "production", "test"] = Field(
        default="development", description="Application environment"
    )
    debug: bool = Field(default=False, description="Debug mode")
    secret_key: SecretStr = Field(
        default=SecretStr("django-insecure-change-me-in-production"),
        description="Django secret key",
    )
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1"],
        description="Allowed hosts",
    )

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    mercadolibre: MercadoLibreSettings = Field(default_factory=MercadoLibreSettings)
    ebay: EbaySettings = Field(default_factory=EbaySettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v: str | list[str]) -> list[str]:
        """Parse allowed hosts from comma-separated string or list."""
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        """Check if running in test environment."""
        return self.environment == "test"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached application settings.

    Uses LRU cache to ensure settings are only loaded once.

    Returns:
        Configured Settings instance.
    """
    return Settings()
