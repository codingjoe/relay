"""Know-how article views — list and detail."""

import pathlib

import frontmatter
from django.conf import settings
from django.http import HttpResponse
from django.template import loader
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html
from abstract.views import (
    BreadcrumbViewMixin,
    CacheControlMixin,
    MarkdownArticleMixin,
    MarkdownView,
)

KNOW_HOW_DIR = pathlib.Path(settings.BASE_DIR) / "know_how" / "docs"
SLUGS = frozenset(p.stem for p in KNOW_HOW_DIR.glob("*.md"))

LICENSE_MARKDOWN = (
    "This work is licensed under a "
    "[Creative Commons Attribution-ShareAlike 4.0 International License]"
    "(https://creativecommons.org/licenses/by-sa/4.0/)."
)

LICENSE_YAML = "CC-BY-SA-4.0"


class KnowHowListView(
    MarkdownArticleMixin, CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView
):
    """Display all know-how articles."""

    template_name = "know_how/list.html"
    title = _("know how")
    parent = "home"
    cache_control = {"public": True, "max_age": 3600}
    docs_dir = KNOW_HOW_DIR
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
            "license": md_2_html(LICENSE_MARKDOWN),
        }


class KnowHowDetailView(MarkdownArticleMixin, MarkdownView):
    """Render a single know-how article."""

    parent = "know_how:list"
    docs_dir = KNOW_HOW_DIR
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
            "license": md_2_html(LICENSE_MARKDOWN),
            "meta_description": metadata.get("description", ""),
            "metadata": metadata,
        }

    def render_markdown(self, request, **kwargs):
        """Return the article as text/markdown with license injected into frontmatter."""
        context = self.get_context_data(**kwargs)
        markdown_text = loader.get_template(self.get_markdown_template()).render(
            context=context, request=request
        )
        metadata, content = frontmatter.parse(markdown_text)
        metadata["license"] = LICENSE_YAML
        frontmatter_str = (
            "---\n"
            + "".join(f"{key}: {value}\n" for key, value in metadata.items())
            + "---\n\n"
        )
        return HttpResponse(
            frontmatter_str + content,
            content_type="text/markdown; charset=utf-8",
        )
