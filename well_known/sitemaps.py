"""Sitemap configuration for all public pages."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from know_how.views import list_articles


class HomeSitemap(Sitemap):
    """Marketing landing page."""

    changefreq = "weekly"
    priority = 1.0

    def items(self):
        return ["home"]

    def location(self, item):
        return reverse(item)


class LegalSitemap(Sitemap):
    """Imprint, terms, and privacy pages."""

    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return ["legal:imprint", "legal:terms", "legal:privacy"]

    def location(self, item):
        return reverse(item)


class KnowHowSitemap(Sitemap):
    """One entry per know-how article."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return [article["slug"] for article in list_articles()]

    def location(self, slug):
        return reverse("know_how:detail", args=[slug])
