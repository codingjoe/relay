from allauth.idp.oidc import views as oidc_views
from django.urls import include, path

from . import views
from .sitemaps import (
    AlternativeToSitemap,
    DocsSitemap,
    HomeSitemap,
    KnowHowSitemap,
    LegalSitemap,
)

app_name = "well_known"

sitemaps = {
    "home": HomeSitemap,
    "legal": LegalSitemap,
    "docs": DocsSitemap,
    "know-how": KnowHowSitemap,
    "alternative-to": AlternativeToSitemap,
}

urlpatterns = [
    path("robots.txt", views.RobotsTxtView.as_view(), name="robots-txt"),
    path("llms.txt", views.LlmsTxtView.as_view(), name="llms-txt"),
    path("llms-full.txt", views.LlmsFullTxtView.as_view(), name="llms-full-txt"),
    path(
        "sitemap.xml",
        views.SitemapView.as_view(),
        {"sitemaps": sitemaps},
        name="sitemap",
    ),
    # https://datatracker.ietf.org/doc/html/rfc8615
    path(
        ".well-known/",
        include(
            [
                # allauth serves the same document as .well-known/openid-configuration.
                # https://datatracker.ietf.org/doc/html/rfc8414
                path(
                    "oauth-authorization-server",
                    oidc_views.configuration,
                    name="oauth-authorization-server",
                ),
                # https://datatracker.ietf.org/doc/html/rfc9728
                path(
                    "oauth-protected-resource",
                    views.OauthProtectedResourceView.as_view(),
                    name="oauth-protected-resource",
                ),
                path(
                    "oauth-protected-resource/mcp",
                    views.OauthProtectedResourceView.as_view(),
                    name="oauth-protected-resource-mcp",
                ),
                path(
                    "mcp.json",
                    views.McpDiscoveryView.as_view(),
                    name="mcp-discovery",
                ),
            ]
        ),
    ),
]
