"""URL configuration for the SMTP service — messages and credentials (org-scoped)."""

from django.urls import include, path

from . import views

app_name = "smtp"

urlpatterns = [
    path(
        "messages/",
        include(
            [
                path("", views.OutgoingMessageLogView.as_view(), name="message-list"),
                path(
                    "<uuid:pk>",
                    views.OutgoingMessageDetailView.as_view(),
                    name="message-detail",
                ),
                path(
                    "<uuid:pk>/modal",
                    views.OutgoingMessageModalView.as_view(),
                    name="message-modal",
                ),
                path("test", views.TestEmailView.as_view(), name="message-test"),
            ]
        ),
    ),
    path(
        "credentials/",
        include(
            [
                path(
                    "", views.SmtpCredentialListView.as_view(), name="credential-list"
                ),
                path(
                    "new",
                    views.SmtpCredentialCreateView.as_view(),
                    name="credential-create",
                ),
                path(
                    "<int:pk>/delete",
                    views.SmtpCredentialDeleteView.as_view(),
                    name="credential-delete",
                ),
            ]
        ),
    ),
]
