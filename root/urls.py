"""URL configuration for the root project."""

from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from health_check.views import HealthCheckView
from redis.asyncio import Redis

from . import views
from .sitemaps import HomeSitemap, KnowHowSitemap, LegalSitemap

sitemaps = {
    "home": HomeSitemap,
    "legal": LegalSitemap,
    "know-how": KnowHowSitemap,
}

urlpatterns = [
    path(
        "health/",
        include(
            [
                path(
                    "django/",
                    HealthCheckView.as_view(
                        checks=[
                            "health_check.Cache",
                            "health_check.Database",
                            "health_check.contrib.psutil.Disk",
                            "health_check.contrib.psutil.Memory",
                            (
                                "health_check.contrib.redis.Redis",
                                {
                                    "client_factory": lambda: Redis.from_url(
                                        settings.REDIS_URL
                                    )
                                },
                            ),
                        ]
                    ),
                    name="home",
                ),
                path(
                    "",
                    HealthCheckView.as_view(
                        checks=[
                            "health_check.contrib.psutil.Disk",
                            "health_check.contrib.psutil.Memory",
                        ]
                    ),
                    name="health",
                ),
            ]
        ),
    ),
    path("", views.HomeView.as_view(), name="home"),
    # Platform (not org-scoped)
    path("", include("accounts.urls")),
    path("legal/", include("legal.urls")),
    path("know-how/", include("know_how.urls")),
    # SEO and agent discovery
    path("robots.txt", views.RobotsTxtView.as_view(), name="robots-txt"),
    path("llms.txt", views.LlmsTxtView.as_view(), name="llms-txt"),
    path("llms-full.txt", views.LlmsFullTxtView.as_view(), name="llms-full-txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="sitemap",
    ),
    # Org-scoped email
    path(
        "org/<slug:org_slug>/email/",
        include(
            [
                path("", include("tx_email.urls")),
                path("", include("smtp.urls")),
                path("", include("mx.urls")),
                path("", include("dmarc.urls")),
                path("domains/", include("domains.urls")),
            ]
        ),
    ),
    # Social auth + admin
    path("", include("social_django.urls")),
    path("admin/", admin.site.urls),
]
