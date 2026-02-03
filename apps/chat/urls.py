"""URL configuration for chat app."""

from django.urls import URLPattern, path

from . import views

app_name = "chat"

urlpatterns: list[URLPattern] = [
    path("", views.index, name="index"),
    path("new/", views.new_conversation, name="new_conversation"),
    path("<uuid:conversation_id>/", views.conversation, name="conversation"),
    path("send/", views.send_message, name="send_message"),
    path("load-more/", views.load_more, name="load_more"),
]
