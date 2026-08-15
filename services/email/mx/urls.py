from django.urls import include, path

from . import views
from .encryption_views import SealedFileKeyView, WebhookEncryptionKeyView

app_name = "mx"

urlpatterns = [
    path(
        "incoming/",
        include(
            [
                path(
                    "<uuid:pk>",
                    views.IncomingMessageDetailView.as_view(),
                    name="message-detail",
                ),
            ]
        ),
    ),
    path(
        "messages/<uuid:pk>/sealed-key/",
        SealedFileKeyView.as_view(),
        name="sealed-file-key",
    ),
    path(
        "webhooks/",
        include(
            [
                path("", views.WebhookListView.as_view(), name="webhook-list"),
                path("new", views.WebhookCreateView.as_view(), name="webhook-create"),
                path(
                    "<int:pk>/delete",
                    views.WebhookDeleteView.as_view(),
                    name="webhook-delete",
                ),
                path(
                    "<int:pk>/test",
                    views.WebhookTestView.as_view(),
                    name="webhook-test",
                ),
                path(
                    "<int:webhook_pk>/encryption-key/",
                    WebhookEncryptionKeyView.as_view(),
                    name="webhook-encryption-key",
                ),
            ]
        ),
    ),
    path(
        "tls/",
        include(
            [
                path(
                    "<uuid:pk>",
                    views.TlsReportDetailView.as_view(),
                    name="tls-report-detail",
                ),
            ]
        ),
    ),
]
