from django.contrib.sitemaps.views import sitemap
from django.urls import path

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
    path("favicon.ico", views.FaviconIcoView.as_view(), name="favicon-ico"),
    path("robots.txt", views.RobotsTxtView.as_view(), name="robots-txt"),
    path("llms.txt", views.LlmsTxtView.as_view(), name="llms-txt"),
    path("llms-full.txt", views.LlmsFullTxtView.as_view(), name="llms-full-txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="sitemap",
    ),
]
