"""URL configuration for domain management (org-scoped)."""

from django.urls import path

from .views import (
    DomainCreateView,
    DomainDetailView,
    DomainListView,
    DomainVerifyView,
)

app_name = "domains"

urlpatterns = [
    path("", DomainListView.as_view(), name="domain_list"),
    path("new", DomainCreateView.as_view(), name="domain_create"),
    path("<int:pk>", DomainDetailView.as_view(), name="domain_detail"),
    path("<int:pk>/verify", DomainVerifyView.as_view(), name="domain_verify"),
]
