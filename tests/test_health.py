"""Tests for health check endpoint."""

from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
class TestHealthCheck:
    """Tests for the health check endpoint."""

    def test_health_check_returns_200(self, test_client: Client) -> None:
        """Health check endpoint should return 200 when healthy."""
        response = test_client.get("/health/")

        assert response.status_code == 200

    def test_health_check_returns_json(self, test_client: Client) -> None:
        """Health check endpoint should return JSON response."""
        response = test_client.get("/health/")

        assert response["Content-Type"] == "application/json"

    def test_health_check_contains_status(self, test_client: Client) -> None:
        """Health check response should contain status field."""
        response = test_client.get("/health/")
        data = response.json()

        assert "status" in data
        assert data["status"] == "healthy"

    def test_health_check_contains_database_check(self, test_client: Client) -> None:
        """Health check response should contain database check."""
        response = test_client.get("/health/")
        data = response.json()

        assert "checks" in data
        assert "database" in data["checks"]
        assert data["checks"]["database"]["status"] == "healthy"

    def test_health_check_returns_503_when_database_unhealthy(
        self, test_client: Client
    ) -> None:
        """Health check should return 503 when database is unhealthy."""
        with patch("core.health.connection") as mock_connection:
            mock_connection.cursor.side_effect = Exception("Database error")
            response = test_client.get("/health/")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["database"]["status"] == "unhealthy"
        assert "Database error" in data["checks"]["database"]["error"]
