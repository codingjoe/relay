"""Alternative-to comparison article views — list and detail."""

import pathlib
from functools import partial

from django.conf import settings
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.markdown_docs import (
    article_path,
    article_title,
    list_articles,
    parse_frontmatter,
)
from abstract.views import BreadcrumbViewMixin, MarkdownView

ALTERNATIVE_TO_DIR = pathlib.Path(settings.BASE_DIR) / "alternative_to" / "docs"

list_comparisons = partial(list_articles, ALTERNATIVE_TO_DIR)
comparison_path = partial(article_path, ALTERNATIVE_TO_DIR)


class AlternativeToListView(BreadcrumbViewMixin, generic.TemplateView):
    """Display all alternative-to comparison articles."""

    template_name = "alternative_to/list.html"
    title = _("Alternative to")
    parent = "home"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": list_comparisons(),
        }


class AlternativeToDetailView(MarkdownView):
    """Render a single alternative-to comparison article."""

    parent = "alternative_to:list"

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs.get("slug", "")
        try:
            return article_title(ALTERNATIVE_TO_DIR, slug)
        except Http404:
            return slug

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        slug = self.kwargs["slug"]
        path = comparison_path(slug)
        text = path.read_text()
        metadata, _ = parse_frontmatter(text)
        context = super().get_context_data(**kwargs)
        context["title"] = metadata.get("name") or article_title(
            ALTERNATIVE_TO_DIR, slug
        )
        context["meta_description"] = metadata.get("description", "")
        return context
