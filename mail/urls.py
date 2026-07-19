"""URL configuration for the email service — messages and test email."""

from django.urls import include, path

from .views import (
    MessageDetailView,
    MessageLogView,
    MessageModalView,
    TestEmailView,
)

app_name = "mail"

urlpatterns = [
    path(
        "messages/",
        include(
            [
                path("", MessageLogView.as_view(), name="message_log"),
                path("<uuid:pk>/", MessageDetailView.as_view(), name="message_detail"),
                path(
                    "<uuid:pk>/modal/",
                    MessageModalView.as_view(),
                    name="message_modal",
                ),
            ]
        ),
    ),
    path("test/", TestEmailView.as_view(), name="test_email"),
]
