"""Views for accounts app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import LoginForm, RegisterForm

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


@require_http_methods(["GET", "POST"])
def register_view(request: HttpRequest) -> HttpResponse:
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect("chat:index")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("chat:index")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest) -> HttpResponse:
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect("chat:index")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("chat:index")
    else:
        form = LoginForm(request)

    return render(request, "accounts/login.html", {"form": form})


@require_GET
@login_required
def logout_view(request: HttpRequest) -> HttpResponse:
    """Handle user logout."""
    logout(request)
    return redirect("accounts:login")


@require_GET
@login_required
def profile_view(request: HttpRequest) -> HttpResponse:
    """Display user profile."""
    return render(request, "accounts/profile.html")
