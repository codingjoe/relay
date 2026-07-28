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
        "dmarc/failures/",
        include(
            [
                path(
                    "",
                    views.DmarcFailureReportListView.as_view(),
                    name="failure-report-list",
                ),
                path(
                    "<int:pk>",
                    views.DmarcFailureReportDetailView.as_view(),
                    name="failure-report-detail",
                ),
            ]
        ),
    ),
]
