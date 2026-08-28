from django.contrib.auth.views import LogoutView
from django.urls import include, path

from . import views

app_name = "accounts"

urlpatterns = [
    path(
        "account/",
        include(
            [
                path("login", views.LoginView.as_view(), name="login"),
                path("logout", LogoutView.as_view(), name="logout"),
            ]
        ),
    ),
    path(
        "organizations/",
        include(
            [
                path("", views.OrganizationListView.as_view(), name="org-list"),
            ]
        ),
    ),
    path(
        "org/<slug:org_slug>/",
        include(
            [
                path(
                    "",
                    views.OrganizationHomeView.as_view(),
                    name="org-home",
                ),
                path(
                    "settings/",
                    include(
                        [
                            path(
                                "",
                                views.OrganizationDetailView.as_view(),
                                name="org-detail",
                            ),
                            path(
                                "edit",
                                views.OrganizationUpdateView.as_view(),
                                name="org-update",
                            ),
                            path(
                                "delete",
                                views.OrganizationDeleteView.as_view(),
                                name="org-delete",
                            ),
                            path(
                                "members/",
                                include(
                                    [
                                        path(
                                            "new",
                                            views.MembershipCreateView.as_view(),
                                            name="member-create",
                                        ),
                                        path(
                                            "<int:member_pk>/delete",
                                            views.MembershipDeleteView.as_view(),
                                            name="member-delete",
                                        ),
                                        path(
                                            "<int:member_pk>/edit",
                                            views.MembershipUpdateView.as_view(),
                                            name="member-update",
                                        ),
                                    ]
                                ),
                            ),
                        ]
                    ),
                ),
            ]
        ),
    ),
]
