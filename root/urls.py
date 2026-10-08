from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from . import views

urlpatterns = [
    path("health/", include("root.health")),
    path("", views.HomeView.as_view(), name="home"),
    path("open-source/", views.OpenSourceView.as_view(), name="open-source"),
    # Platform (not org-scoped)
    path("", include("accounts.urls")),
    path("legal/", include("legal.urls")),
    path("docs/", include("docs.urls")),
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

if settings.DEBUG:
    urlpatterns = [
        *urlpatterns,
        path("__debug__/", include("debug_toolbar.urls")),
        path("emails/", include("django_letter.urls")),
    ]
