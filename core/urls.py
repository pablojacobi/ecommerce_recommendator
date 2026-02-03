"""
URL configuration for ecommerce_recommendator project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Landing page
    path("", TemplateView.as_view(template_name="landing.html"), name="landing"),
    # Admin
    path("admin/", admin.site.urls),
    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger"),
    # Apps
    path("chat/", include("apps.chat.urls", namespace="chat")),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    # API
    path("api/v1/", include("apps.api.urls", namespace="api")),
    # Health check
    path("health/", include("core.health_urls")),
]

# Debug toolbar (development only)
if settings.DEBUG:
    try:
        import debug_toolbar
        from django.urls import URLResolver

        debug_patterns: list[URLResolver] = [
            path("__debug__/", include(debug_toolbar.urls)),
        ]
        urlpatterns = [*debug_patterns, *urlpatterns]
    except ImportError:
        pass
