from django.urls import include, path

from tx_mail.views import MergedMessagesRedirectView

from . import views

app_name = "smtp"

urlpatterns = [
    path(
        "messages/",
        include(
            [
                path(
                    "",
                    MergedMessagesRedirectView.as_view(direction="sent"),
                    name="message-list",
                ),
                path(
                    "<uuid:pk>",
                    views.OutgoingMessageDetailView.as_view(),
                    name="message-detail",
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
