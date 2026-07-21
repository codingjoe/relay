"""URL configuration for the transactional email dashboard."""

from django.urls import path

from . import views

app_name = "tx_email"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
]
