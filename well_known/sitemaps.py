"""Sitemap configuration for all public pages."""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from alternative_to.content import AlternativeToContent
from docs.content import DocsContent
from know_how.content import KnowHowContent


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


class DocsSitemap(Sitemap):
    """One entry per product documentation article."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return [slug for slug, _ in DocsContent.get_articles()]

    def location(self, slug):
        return reverse("docs:detail", args=[slug])


class KnowHowSitemap(Sitemap):
    """One entry per know-how article."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return [slug for slug, _ in KnowHowContent.get_articles()]

    def location(self, slug):
        return reverse("know_how:detail", args=[slug])


class AlternativeToSitemap(Sitemap):
    """One entry per alternative-to comparison article."""

    changefreq = "monthly"
    priority = 0.6

    def items(self):
        return [slug for slug, _ in AlternativeToContent.get_articles()]

    def location(self, slug):
        return reverse("alternative_to:detail", args=[slug])
