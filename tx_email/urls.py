from django.urls import path

from . import views

app_name = "tx_email"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path(
        "api/charts/<str:chart_type>/",
        views.ChartDataView.as_view(),
        name="chart-data",
    ),
]
