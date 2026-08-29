import pathlib

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html
from abstract.views import (
    BreadcrumbViewMixin,
    CacheControlMixin,
    MarkdownArticleMixin,
    MarkdownView,
)

DOCS_DIR = pathlib.Path(settings.BASE_DIR) / "docs" / "docs"
SLUGS = frozenset(p.stem for p in DOCS_DIR.glob("*.md"))


class DocsListView(
    MarkdownArticleMixin, CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView
):
    """Display all product documentation articles."""

    template_name = "docs/list.html"
    title = _("Docs")
    parent = "home"
    cache_control = {"public": True, "max_age": 3600}
    docs_dir = DOCS_DIR
    slugs = SLUGS

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": [
                {
                    "slug": slug,
                    "title": metadata["name"],
                    "description": md_2_html(metadata.get("description", "")),
                }
                for slug, metadata in self.get_articles()
            ],
        }


class DocsDetailView(MarkdownArticleMixin, MarkdownView):
    """Render a single product documentation article."""

    parent = "docs:list"
    docs_dir = DOCS_DIR
    slugs = SLUGS

    @classmethod
    def get_title(cls, request):
        return cls.get_article_metadata(request.resolver_match.kwargs["slug"])["name"]

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        metadata = self.get_article_metadata(self.kwargs["slug"])
        return super().get_context_data(**kwargs) | {
            "title": metadata["name"],
            "meta_description": metadata.get("description", ""),
        }
