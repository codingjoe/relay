"""Know-how article views — list and detail."""

import pathlib
from functools import partial

from django.conf import settings
from django.http import Http404, HttpResponse
from django.template import loader
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.markdown_docs import (
    article_path,
    extract_title,
    list_articles,
    parse_frontmatter,
)
from abstract.utils import md_2_html
from abstract.views import BreadcrumbViewMixin, CacheControlMixin, MarkdownView

KNOW_HOW_DIR = pathlib.Path(settings.BASE_DIR) / "know_how" / "docs"

LICENSE_MARKDOWN = (
    "This work is licensed under a "
    "[Creative Commons Attribution-ShareAlike 4.0 International License]"
    "(https://creativecommons.org/licenses/by-sa/4.0/)."
)

LICENSE_YAML = "CC-BY-SA-4.0"


list_articles = partial(list_articles, KNOW_HOW_DIR)
article_path = partial(article_path, KNOW_HOW_DIR)


class KnowHowListView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Display all know-how articles."""

    template_name = "know_how/list.html"
    title = _("know how")
    parent = "home"
    cache_control = {"public": True, "max_age": 3600}

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": list_articles(),
            "license": md_2_html(LICENSE_MARKDOWN),
        }


class KnowHowDetailView(MarkdownView):
    """Render a single know-how article."""

    parent = "know_how:list"

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs.get("slug", "")
        try:
            path = article_path(slug)
        except Http404:
            return slug
        text = path.read_text()
        metadata, _ = parse_frontmatter(text)
        return metadata.get("name") or extract_title(text)

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        slug = self.kwargs["slug"]
        path = article_path(slug)
        text = path.read_text()
        metadata, _ = parse_frontmatter(text)
        context = super().get_context_data(**kwargs)
        context["title"] = metadata.get("name") or extract_title(text)
        context["license"] = md_2_html(LICENSE_MARKDOWN)
        context["meta_description"] = metadata.get("description", "")
        return context

    def render_markdown(self, request, **kwargs):
        """Return the article as `text/markdown` with license injected into frontmatter."""
        context = self.get_context_data(**kwargs)
        markdown_text = loader.get_template(self.get_markdown_template()).render(
            context=context, request=request
        )
        metadata, content = parse_frontmatter(markdown_text)
        metadata["license"] = LICENSE_YAML
        frontmatter = (
            "---\n"
            + "".join(f"{key}: {value}\n" for key, value in metadata.items())
            + "---\n\n"
        )
        return HttpResponse(
            frontmatter + content,
            content_type="text/markdown; charset=utf-8",
        )
