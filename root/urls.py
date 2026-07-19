"""URL configuration for the root project."""

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
    # Platform
    path("", include("domains.urls")),
    path("", include("accounts.urls")),
    path("", include("legal.urls")),
    # Email service
    path("email/", include("mail.urls")),
    path("email/", include("smtp.urls")),
    # Social auth
    path("", include("social_django.urls")),
    path("admin/", admin.site.urls),
]
