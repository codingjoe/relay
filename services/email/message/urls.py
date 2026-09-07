from django.urls import include, path

from . import views

app_name = "message"

urlpatterns = [
    path(
        "messages/",
        include(
            [
                path("", views.MessageListView.as_view(), name="message-list"),
                path(
                    "<uuid:pk>/download",
                    views.MessageDownloadView.as_view(),
                    name="message-download",
                ),
            ]
        ),
    ),
    path(
        "certificates/",
        include(
            [
                path(
                    "<slug:fingerprint>",
                    views.CertificateDetailView.as_view(),
                    name="certificate-detail",
                ),
            ]
        ),
    ),
]
