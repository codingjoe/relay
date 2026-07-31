"""Know-how article views — list and detail."""

import pathlib

from django.conf import settings
from django.http import Http404, HttpResponse
from django.template import loader
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html, strip_frontmatter
from abstract.views import BreadcrumbViewMixin, MarkdownView

KNOW_HOW_DIR = pathlib.Path(settings.BASE_DIR) / "know_how" / "docs"

ARTICLE_SLUGS = (
    frozenset(p.stem for p in KNOW_HOW_DIR.glob("*.md"))
    if KNOW_HOW_DIR.exists()
    else frozenset()
)

LICENSE_MARKDOWN = (
    "This work is licensed under a "
    "[Creative Commons Attribution-ShareAlike 4.0 International License]"
    "(https://creativecommons.org/licenses/by-sa/4.0/)."
)

LICENSE_YAML = "CC-BY-SA-4.0"


def parse_frontmatter(text):
    """Extract YAML frontmatter and content from a Markdown document."""
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            frontmatter = "".join(lines[1:i])
            content = "".join(lines[i + 1 :]).lstrip("\n")
            metadata = {}
            for fm_line in frontmatter.splitlines():
                if ":" in fm_line:
                    key, value = fm_line.split(":", 1)
                    metadata[key.strip()] = value.strip().strip("\"'")
            return metadata, content
    return {}, text


def list_articles():
    """Return all know-how articles with slug, title, and rendered description."""
    articles = []
    for slug in sorted(ARTICLE_SLUGS):
        text = (KNOW_HOW_DIR / f"{slug}.md").read_text()
        metadata, _ = parse_frontmatter(text)
        title = metadata.get("name") or extract_title(text)
        if not title:
            continue
        articles.append(
            {
                "slug": slug,
                "title": title,
                "description": md_2_html(metadata.get("description", "")),
            }
        )
    return articles


def extract_title(markdown_text):
    """Return the first H1 heading text from the given Markdown."""
    markdown_text = strip_frontmatter(markdown_text)
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def article_path(slug):
    """Resolve the filesystem path for a know-how article or raise Http404."""
    if slug not in ARTICLE_SLUGS:
        raise Http404("Article not found")
    return KNOW_HOW_DIR / f"{slug}.md"


class KnowHowListView(BreadcrumbViewMixin, generic.TemplateView):
    """Display all know-how articles."""

    template_name = "know_how/list.html"
    title = _("know how")
    parent = "home"

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
        """Return the article as ``text/markdown`` with license injected into frontmatter."""
        context = self.get_context_data(**kwargs)
        markdown_text = loader.get_template(self.get_markdown_template()).render(
            context=context, request=request
        )
        metadata, content = parse_frontmatter(markdown_text)
        metadata["license"] = LICENSE_YAML
        frontmatter = "---\n"
        for key, value in metadata.items():
            frontmatter += f"{key}: {value}\n"
        frontmatter += "---\n\n"
        return HttpResponse(
            frontmatter + content,
            content_type="text/markdown; charset=utf-8",
        )
