from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from services.mcp.oidc import AuthorizationView

from . import views

urlpatterns = [
    path("health/", include("root.health")),
    path("", views.HomeView.as_view(), name="home"),
    path("open-source/", views.OpenSourceView.as_view(), name="open-source"),
    path("debug/form/", views.DebugFormView.as_view(), name="debug-form"),
    # Platform (not org-scoped)
    path("", include("accounts.urls")),
    path("legal/", include("legal.urls")),
    path("docs/", include("docs.urls")),
    path("know-how/", include("know_how.urls")),
    path("alternative-to/", include("alternative_to.urls")),
    # Site-root crawler files and the discovery documents under /.well-known/
    path("", include("well_known.urls")),
    # Org-scoped email
    path(
        "org/<slug:org_slug>/email/",
        include(
            [
                path("", include("services.email.message.urls")),
                path("", include("services.email.dashboard.urls")),
                path("", include("services.email.msa.urls")),
                path("", include("services.email.mta.urls")),
                path("", include("services.email.dmarc.urls")),
                path("", include("services.email.reputation.urls")),
                path("domains/", include("domains.urls")),
            ]
        ),
    ),
    # Org-scoped MCP
    path("org/<slug:org_slug>/mcp/", include("services.mcp.urls")),
    # OIDC provider for MCP clients
    # https://docs.allauth.org/en/latest/idp/
    path("identity/o/authorize", AuthorizationView.as_view()),
    path("", include("allauth.idp.urls")),
    path("social/", include("allauth.urls")),
    path("admin/", admin.site.urls),
]

if settings.DEBUG:
    urlpatterns = [
        *urlpatterns,
        path("__debug__/", include("debug_toolbar.urls")),
        path("emails/", include("django_letter.urls")),
    ]
