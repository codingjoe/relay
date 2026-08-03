from django.urls import path

from . import views

app_name = "dmarc"

urlpatterns = [
    path(
        "dmarc/<uuid:pk>",
        views.DmarcReportDetailView.as_view(),
        name="report-detail",
    ),
    path(
        "dmarc/failures/<uuid:pk>",
        views.DmarcFailureReportDetailView.as_view(),
        name="failure-report-detail",
    ),
]
