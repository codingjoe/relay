"""URL configuration for accounts — auth, organizations, and org settings."""

from django.contrib.auth.views import LogoutView
from django.urls import include, path

from .views import (
    LoginView,
    MembershipCreateView,
    MembershipDeleteView,
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
            ]
        ),
    ),
    path(
        "org/<int:org_pk>/settings/",
        include(
            [
                path(
                    "",
                    OrganizationDetailView.as_view(),
                    name="organization_detail",
                ),
                path(
                    "edit",
                    OrganizationUpdateView.as_view(),
                    name="organization_update",
                ),
                path(
                    "delete",
                    OrganizationDeleteView.as_view(),
                    name="organization_delete",
                ),
                path(
                    "members/new",
                    MembershipCreateView.as_view(),
                    name="membership_create",
                ),
                path(
                    "members/<int:member_pk>/delete",
                    MembershipDeleteView.as_view(),
                    name="membership_delete",
                ),
            ]
        ),
    ),
]
