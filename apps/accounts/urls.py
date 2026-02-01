"""URL configuration for accounts app."""

from django.urls import URLPattern, path

from . import views

app_name = "accounts"

urlpatterns: list[URLPattern] = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
]
