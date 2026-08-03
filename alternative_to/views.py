"""Alternative-to comparison article views — list and detail."""

import pathlib

from django.conf import settings
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html
from abstract.views import BreadcrumbViewMixin, MarkdownArticleMixin, MarkdownView

ALTERNATIVE_TO_DIR = pathlib.Path(settings.BASE_DIR) / "alternative_to" / "docs"
SLUGS = frozenset(p.stem for p in ALTERNATIVE_TO_DIR.glob("*.md"))


class AlternativeToListView(
    MarkdownArticleMixin, BreadcrumbViewMixin, generic.TemplateView
):
    """Display all alternative-to comparison articles."""

    template_name = "alternative_to/list.html"
    title = _("Alternative to")
    parent = "home"
    docs_dir = ALTERNATIVE_TO_DIR
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


class AlternativeToDetailView(MarkdownArticleMixin, MarkdownView):
    """Render a single alternative-to comparison article."""

    parent = "alternative_to:list"
    docs_dir = ALTERNATIVE_TO_DIR
    slugs = SLUGS

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs.get("slug", "")
        try:
            return cls.get_article_metadata(slug)["name"]
        except Http404:
            return slug

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        metadata = self.get_article_metadata(self.kwargs["slug"])
        return super().get_context_data(**kwargs) | {
            "title": metadata["name"],
            "meta_description": metadata.get("description", ""),
            "metadata": metadata,
        }
