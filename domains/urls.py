from django.urls import include, path

from . import views

app_name = "domains"

urlpatterns = [
    path("", views.DomainListView.as_view(), name="domain-list"),
    path("new", views.DomainCreateView.as_view(), name="domain-create"),
    path(
        "<int:pk>/",
        include(
            [
                path("", views.DomainDetailView.as_view(), name="domain-detail"),
                path("delete", views.DomainDeleteView.as_view(), name="domain-delete"),
                path("verify", views.DomainVerifyView.as_view(), name="domain-verify"),
                path(
                    "delegate-apex",
                    views.DomainDelegateApexView.as_view(),
                    name="domain-delegate-apex",
                ),
            ]
        ),
    ),
]
