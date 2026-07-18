"""URL configuration for domain management."""

from django.urls import include, path

from .views import (
    DashboardView,
    DomainCreateView,
    DomainDetailView,
    DomainListView,
    DomainVerifyView,
    TestEmailView,
)

app_name = "domains"

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path(
        "domains/",
        include(
            [
                path("", DomainListView.as_view(), name="domain_list"),
                path("new", DomainCreateView.as_view(), name="domain_create"),
                path("<int:pk>", DomainDetailView.as_view(), name="domain_detail"),
                path(
                    "<int:pk>/verify",
                    DomainVerifyView.as_view(),
                    name="domain_verify",
                ),
            ]
        ),
    ),
    path("test-email/", TestEmailView.as_view(), name="test_email"),
]
