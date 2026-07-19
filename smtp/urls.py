"""URL configuration for SMTP credentials."""

from django.urls import include, path

from .views import (
    SmtpCredentialCreateView,
    SmtpCredentialDeleteView,
    SmtpCredentialListView,
)

app_name = "smtp"

urlpatterns = [
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
