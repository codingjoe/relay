"""URL configuration for mail message views."""

from django.urls import path

from .views import MessageDetailView, MessageLogView, MessageModalView

app_name = "mail"

urlpatterns = [
    path("email/", MessageLogView.as_view(), name="message_log"),
    path("email/<uuid:pk>/", MessageDetailView.as_view(), name="message_detail"),
    path("email/<uuid:pk>/modal/", MessageModalView.as_view(), name="message_modal"),
]
