from django.urls import path

from . import views

app_name = "email-dashboard"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path(
        "api/charts/<str:chart_type>/",
        views.ChartDataView.as_view(),
        name="chart-data",
    ),
    path(
        "contacts/reports/",
        views.ContactReportsView.as_view(),
        name="contact-reports",
    ),
]
