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
        "messages/<uuid:pk>/body",
        views.MessageBodyView.as_view(),
        name="message-body",
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
