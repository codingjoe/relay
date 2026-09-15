from django.template import loader
from django.urls import reverse
from django.views import generic

from abstract.utils import strip_frontmatter
from abstract.views import CacheControlMixin
from alternative_to.views import AlternativeToListView
from docs.views import DocsListView
from know_how.views import KnowHowListView


class RobotsTxtView(CacheControlMixin, generic.TemplateView):
    """Serve robots.txt with a sitemap reference."""

    template_name = "well_known/robots.txt"
    content_type = "text/plain; charset=utf-8"
    cache_control = {"public": True, "max_age": 3600}

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "sitemap_url": self.request.build_absolute_uri(
                reverse("well_known:sitemap")
            ),
        }


class LlmsTxtView(CacheControlMixin, generic.TemplateView):
    """Serve llms.txt following the llmstxt.org spec."""

    template_name = "well_known/llms.txt"
    content_type = "text/plain; charset=utf-8"
    cache_control = {"public": True, "max_age": 3600}

    def get_context_data(self, **kwargs):
        docs_articles = [
            {
                "title": metadata["name"],
                "url": self.request.build_absolute_uri(
                    reverse("docs:detail", args=[slug])
                ),
            }
            for slug, metadata in DocsListView.get_articles()
        ]
        articles = [
            {
                "title": metadata["name"],
                "url": self.request.build_absolute_uri(
                    reverse("know_how:detail", args=[slug])
                ),
            }
            for slug, metadata in KnowHowListView.get_articles()
        ]
        legal_pages = [
            {"title": label, "url": self.request.build_absolute_uri(reverse(name))}
            for name, label in [
                ("legal:imprint", "Imprint"),
                ("legal:terms", "Terms of Service"),
                ("legal:privacy", "Privacy Policy"),
            ]
        ]
        comparisons = [
            {
                "title": metadata["name"],
                "url": self.request.build_absolute_uri(
                    reverse("alternative_to:detail", args=[slug])
                ),
            }
            for slug, metadata in AlternativeToListView.get_articles()
        ]
        return super().get_context_data(**kwargs) | {
            "docs_articles": docs_articles,
            "articles": articles,
            "legal_pages": legal_pages,
            "comparisons": comparisons,
        }


class LlmsFullTxtView(CacheControlMixin, generic.TemplateView):
    """Serve llms-full.txt with the full content of all documentation articles."""

    template_name = "well_known/llms-full.txt"
    content_type = "text/plain; charset=utf-8"
    cache_control = {"public": True, "max_age": 3600}

    def get_context_data(self, **kwargs):
        docs_articles = [
            {
                "title": metadata["name"],
                "url": self.request.build_absolute_uri(
                    reverse("docs:detail", args=[slug])
                ),
                "content": strip_frontmatter(
                    loader.get_template(f"{slug}.md").render(request=self.request)
                ),
            }
            for slug, metadata in DocsListView.get_articles()
        ]
        articles = [
            {
                "title": metadata["name"],
                "url": self.request.build_absolute_uri(
                    reverse("know_how:detail", args=[slug])
                ),
                "content": strip_frontmatter(
                    loader.get_template(f"{slug}.md").render(request=self.request)
                ),
            }
            for slug, metadata in KnowHowListView.get_articles()
        ]
        return super().get_context_data(**kwargs) | {
            "docs_articles": docs_articles,
            "articles": articles,
            "comparisons": [
                {
                    "title": metadata["name"],
                    "url": self.request.build_absolute_uri(
                        reverse("alternative_to:detail", args=[slug])
                    ),
                    "content": strip_frontmatter(
                        loader.get_template(f"{slug}.md").render(request=self.request)
                    ),
                }
                for slug, metadata in AlternativeToListView.get_articles()
            ],
        }
