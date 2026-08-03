from django.urls import include, path

from . import views

app_name = "dmarc"

urlpatterns = [
    path(
        "dmarc/",
        include(
            [
                path(
                    "<uuid:pk>",
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
                    "<uuid:pk>",
                    views.DmarcFailureReportDetailView.as_view(),
                    name="failure-report-detail",
                ),
            ]
        ),
    ),
]
