"""URL configuration for the SMTP service — messages and credentials."""

from django.urls import include, path

from .views import (
    OutgoingMessageDetailView,
    OutgoingMessageLogView,
    OutgoingMessageModalView,
    SmtpCredentialCreateView,
    SmtpCredentialDeleteView,
    SmtpCredentialListView,
    TestEmailView,
)

app_name = "smtp"

urlpatterns = [
    path(
        "messages/",
        include(
            [
                path("", OutgoingMessageLogView.as_view(), name="message_log"),
                path(
                    "<uuid:pk>",
                    OutgoingMessageDetailView.as_view(),
                    name="message_detail",
                ),
                path(
                    "<uuid:pk>/modal",
                    OutgoingMessageModalView.as_view(),
                    name="message_modal",
                ),
            ]
        ),
    ),
    path("test", TestEmailView.as_view(), name="test_email"),
    path(
        "credentials/",
        include(
            [
                path("", SmtpCredentialListView.as_view(), name="credential_list"),
                path(
                    "new", SmtpCredentialCreateView.as_view(), name="credential_create"
                ),
                path(
                    "<int:pk>/delete",
                    SmtpCredentialDeleteView.as_view(),
                    name="credential_delete",
                ),
            ]
        ),
    ),
]
