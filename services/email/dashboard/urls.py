from django.urls import path

from . import views

app_name = "email-dashboard"

urlpatterns = [
    path("", views.GetStartedView.as_view(), name="get-started"),
    path(
        "reports/",
        views.ReportListView.as_view(),
        name="report-list",
    ),
]
