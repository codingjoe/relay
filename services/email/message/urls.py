from django.urls import include, path

from . import views

app_name = "message"

urlpatterns = [
    path(
        "messages/",
        views.MessageListView.as_view(),
        name="message-list",
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
