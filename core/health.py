"""Health check endpoint for monitoring."""

from django.db import connection
from django.http import JsonResponse


def health_check(_request: object) -> JsonResponse:
    """
    Health check endpoint.

    Returns basic health status. Will be expanded in later PRs
    to include database, cache, and external service checks.

    Args:
        _request: Django HTTP request object (unused but required by Django).

    Returns:
        JsonResponse with health status.
    """
    checks: dict[str, dict[str, str]] = {
        "database": _check_database(),
    }

    # Determine overall status
    all_healthy = all(check.get("status") == "healthy" for check in checks.values())

    health_status = {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
    }

    return JsonResponse(
        health_status,
        status=200 if all_healthy else 503,
    )


def _check_database() -> dict[str, str]:
    """Check database connectivity."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
