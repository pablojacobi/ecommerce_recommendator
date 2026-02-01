"""URL configuration for the API application."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.views import (
    ConversationViewSet,
    HealthCheckView,
    MarketplacesView,
    MessageViewSet,
)

app_name = "api"

router = DefaultRouter()
router.register(r"conversations", ConversationViewSet, basename="conversation")
router.register(r"messages", MessageViewSet, basename="message")

urlpatterns = [
    path("", include(router.urls)),
    path("marketplaces/", MarketplacesView.as_view(), name="marketplaces"),
    path("health/", HealthCheckView.as_view(), name="health"),
]
