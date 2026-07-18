"""URL configuration for accounts — auth and credentials."""

from django.contrib.auth.views import LogoutView
from django.urls import include, path

from .views import (
    CredentialCreateView,
    CredentialDeleteView,
    CredentialListView,
    LoginView,
)

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "credentials/",
        include(
            [
                path("", CredentialListView.as_view(), name="credential_list"),
                path("new", CredentialCreateView.as_view(), name="credential_create"),
                path(
                    "<int:pk>/delete",
                    CredentialDeleteView.as_view(),
                    name="credential_delete",
                ),
            ]
        ),
    ),
]
