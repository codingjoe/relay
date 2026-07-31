from django.urls import include, path

from tx_mail.views import MergedReportsRedirectView

from . import views

app_name = "dmarc"

urlpatterns = [
    path(
        "dmarc/",
        include(
            [
                path(
                    "",
                    MergedReportsRedirectView.as_view(report_type="dmarc"),
                    name="report-list",
                ),
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
                    "",
                    MergedReportsRedirectView.as_view(report_type="failures"),
                    name="failure-report-list",
                ),
                path(
                    "<uuid:pk>",
                    views.DmarcFailureReportDetailView.as_view(),
                    name="failure-report-detail",
                ),
            ]
        ),
    ),
]
