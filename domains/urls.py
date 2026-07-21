"""URL configuration for domain management (org-scoped)."""

from django.urls import path

from . import views

app_name = "domains"

urlpatterns = [
    path("", views.DomainListView.as_view(), name="domain-list"),
    path("new", views.DomainCreateView.as_view(), name="domain-create"),
    path("<int:pk>", views.DomainDetailView.as_view(), name="domain-detail"),
    path("<int:pk>/delete", views.DomainDeleteView.as_view(), name="domain-delete"),
    path("<int:pk>/verify", views.DomainVerifyView.as_view(), name="domain-verify"),
]
