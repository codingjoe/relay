from django.urls import include, path

from . import views

app_name = "dmarc"

urlpatterns = [
    path(
        "dmarc/",
        include(
            [
                path("", views.DmarcReportListView.as_view(), name="report-list"),
                path(
                    "<int:pk>",
                    views.DmarcReportDetailView.as_view(),
                    name="report-detail",
                ),
            ]
        ),
    ),
    path(
        "tls/",
        include(
            [
                path("", views.TlsReportListView.as_view(), name="tls-report-list"),
                path(
                    "<int:pk>",
                    views.TlsReportDetailView.as_view(),
                    name="tls-report-detail",
                ),
            ]
        ),
    ),
]
