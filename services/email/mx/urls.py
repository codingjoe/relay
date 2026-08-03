from django.urls import include, path

from . import views

app_name = "mx"

urlpatterns = [
    path(
        "inbox/<uuid:pk>",
        views.IncomingMessageDetailView.as_view(),
        name="message-detail",
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
            ]
        ),
    ),
    path(
        "tls/<uuid:pk>",
        views.TlsReportDetailView.as_view(),
        name="tls-report-detail",
    ),
]
