"""URL configuration for accounts — auth, organizations, and members."""

from django.contrib.auth.views import LogoutView
from django.urls import include, path

from .views import (
    LoginView,
    MembershipCreateView,
    MembershipDeleteView,
    OrganizationCreateView,
    OrganizationDeleteView,
    OrganizationDetailView,
    OrganizationListView,
    OrganizationUpdateView,
)

app_name = "accounts"

urlpatterns = [
    path(
        "account/",
        include(
            [
                path("login", LoginView.as_view(), name="login"),
                path("logout", LogoutView.as_view(), name="logout"),
            ]
        ),
    ),
    path(
        "organizations/",
        include(
            [
                path("", OrganizationListView.as_view(), name="organization_list"),
                path(
                    "new", OrganizationCreateView.as_view(), name="organization_create"
                ),
                path(
                    "<slug:slug>",
                    OrganizationDetailView.as_view(),
                    name="organization_detail",
                ),
                path(
                    "<slug:slug>/edit",
                    OrganizationUpdateView.as_view(),
                    name="organization_update",
                ),
                path(
                    "<slug:slug>/delete",
                    OrganizationDeleteView.as_view(),
                    name="organization_delete",
                ),
                path(
                    "<slug:slug>/members/new",
                    MembershipCreateView.as_view(),
                    name="membership_create",
                ),
                path(
                    "<slug:slug>/members/<int:pk>/delete",
                    MembershipDeleteView.as_view(),
                    name="membership_delete",
                ),
            ]
        ),
    ),
]
