"""URL configuration for accounts — auth, organizations, and members."""

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
                path(
                    "<int:pk>",
                    OrganizationDetailView.as_view(),
                    name="organization_detail",
                ),
                path(
                    "<int:pk>/edit",
                    OrganizationUpdateView.as_view(),
                    name="organization_update",
                ),
                path(
                    "<int:pk>/delete",
                    OrganizationDeleteView.as_view(),
                    name="organization_delete",
                ),
                path(
                    "<int:pk>/members/new",
                    MembershipCreateView.as_view(),
                    name="membership_create",
                ),
                path(
                    "<int:pk>/members/<int:member_pk>/delete",
                    MembershipDeleteView.as_view(),
                    name="membership_delete",
                ),
            ]
        ),
    ),
]
