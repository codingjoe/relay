"""Sitemap configuration for all public pages."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from knowhow.views import list_articles


class HomeSitemap(Sitemap):
    """The marketing landing page."""

    changefreq = "weekly"
    priority = 1.0

    def items(self):
        return ["home"]

    def location(self, item):
        return reverse(item)


class LegalSitemap(Sitemap):
    """Static legal pages — imprint, terms, privacy."""

    changefreq = "monthly"
    priority = 0.3

    def items(self):
        return ["legal:imprint", "legal:terms", "legal:privacy"]

    def location(self, item):
        return reverse(item)


class KnowHowSitemap(Sitemap):
    """Know-how articles — one entry per Markdown file."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return [article["slug"] for article in list_articles()]

    def location(self, slug):
        return reverse("knowhow:detail", args=[slug])
