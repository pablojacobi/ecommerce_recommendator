"""Views for chat app."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


@login_required
def index(request: HttpRequest) -> HttpResponse:
    """Display the chat interface."""
    return render(request, "chat/index.html")
