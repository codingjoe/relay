from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from health_check.views import HealthCheckView
from redis.asyncio import Redis

from . import views

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
    path("open-source/", views.OpenSourceView.as_view(), name="open-source"),
    # Platform (not org-scoped)
    path("", include("accounts.urls")),
    path("legal/", include("legal.urls")),
    path("know-how/", include("know_how.urls")),
    path("alternative-to/", include("alternative_to.urls")),
    # Well-known endpoints. Robots.txt, llms.txt, sitemap.xml
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
    # Social auth + admin
    path("", include("social_django.urls")),
    path("admin/", admin.site.urls),
]
