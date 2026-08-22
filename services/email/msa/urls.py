from django.urls import include, path

from . import views

app_name = "msa"

urlpatterns = [
    path(
        "messages/",
        include(
            [
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
                path("", views.MsaCredentialListView.as_view(), name="credential-list"),
                path(
                    "new",
                    views.MsaCredentialCreateView.as_view(),
                    name="credential-create",
                ),
                path(
                    "<int:pk>/delete",
                    views.MsaCredentialDeleteView.as_view(),
                    name="credential-delete",
                ),
            ]
        ),
    ),
    path(
        "suppression/",
        include(
            [
                path(
                    "",
                    views.SuppressionListView.as_view(),
                    name="suppression-list",
                ),
                path(
                    "add",
                    views.SuppressionCreateView.as_view(),
                    name="suppression-add",
                ),
                path(
                    "remove",
                    views.SuppressionRemoveView.as_view(),
                    name="suppression-remove",
                ),
                path(
                    "check",
                    views.SuppressionCheckView.as_view(),
                    name="suppression-check",
                ),
            ]
        ),
    ),
]
