"""URL configuration for the transactional email dashboard."""

from django.urls import path

from .views import DashboardView

app_name = "tx_email"

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
]
