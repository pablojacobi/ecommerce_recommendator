"""URL configuration for chat app."""

from django.urls import URLPattern, path

from . import views

app_name = "chat"

urlpatterns: list[URLPattern] = [
    path("", views.index, name="index"),
]
