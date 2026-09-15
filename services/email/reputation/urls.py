from django.urls import include, path

from . import views

app_name = "reputation"

urlpatterns = [
    path(
        "reputation/",
        include(
            [
                path("", views.ReputationOverviewView.as_view(), name="overview"),
                path(
                    "fbl/",
                    include(
                        [
                            path(
                                "",
                                views.FblReportListView.as_view(),
                                name="fbl-report-list",
                            ),
                            path(
                                "<uuid:pk>",
                                views.FblReportDetailView.as_view(),
                                name="fbl-report-detail",
                            ),
                        ]
                    ),
                ),
            ]
        ),
    ),
]
