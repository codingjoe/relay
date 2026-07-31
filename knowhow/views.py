"""Know-how article views — list and detail."""

import pathlib

from django.conf import settings
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html
from abstract.views import BreadcrumbViewMixin, MarkdownView

KNOW_HOW_DIR = pathlib.Path(settings.BASE_DIR) / "knowhow" / "docs"

LICENSE_MARKDOWN = (
    "This work is licensed under a "
    "[Creative Commons Attribution-ShareAlike 4.0 International License]"
    "(https://creativecommons.org/licenses/by-sa/4.0/)."
)


def parse_frontmatter(markdown_text):
    """Parse YAML frontmatter from the start of a Markdown file.

    Returns a tuple of (metadata dict, content without frontmatter).
    If the file has no frontmatter, returns ({}, full_text).
    """
    stripped = markdown_text.lstrip()
    if not stripped.startswith("---"):
        return {}, markdown_text
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}, markdown_text
    metadata = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip()
    return metadata, parts[2].lstrip("\n")


def list_articles():
    """Return a list of articles as dicts with slug, title, and description.

    Each Markdown file in the know-how directory becomes one article.
    Title and description come from the YAML frontmatter.
    """
    articles = []
    if not KNOW_HOW_DIR.exists():
        return articles
    for path in sorted(KNOW_HOW_DIR.glob("*.md")):
        metadata, _ = parse_frontmatter(path.read_text())
        title = metadata.get("name") or extract_title(path.read_text())
        if not title:
            continue
        articles.append(
            {
                "slug": path.stem,
                "title": title,
                "description": metadata.get("description", ""),
                "author": metadata.get("author", ""),
            }
        )
    return articles


def extract_title(markdown_text):
    """Return the text of the first H1 heading in the given Markdown."""
    _, content = parse_frontmatter(markdown_text)
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


class KnowHowListView(BreadcrumbViewMixin, generic.TemplateView):
    """List all know-how articles."""

    template_name = "knowhow/list.html"
    title = _("know how")
    parent = "home"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": list_articles(),
            "license": md_2_html(LICENSE_MARKDOWN),
        }


class KnowHowDetailView(MarkdownView):
    """Render a single know-how article by slug."""

    parent = "knowhow:list"

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs.get("slug", "")
        path = KNOW_HOW_DIR / f"{slug}.md"
        if path.exists():
            metadata, _ = parse_frontmatter(path.read_text())
            return metadata.get("name") or extract_title(path.read_text())
        return slug

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        slug = self.kwargs["slug"]
        path = KNOW_HOW_DIR / f"{slug}.md"
        if not path.exists():
            raise Http404("Article not found")
        metadata, _ = parse_frontmatter(path.read_text())
        context = super().get_context_data(**kwargs)
        context["license"] = md_2_html(LICENSE_MARKDOWN)
        context["meta_description"] = metadata.get("description", "")
        context["author"] = metadata.get("author", "")
        return context

    def render_markdown(self, request, **kwargs):
        response = super().render_markdown(request, **kwargs)
        license_md = f"\n\n---\n\n{LICENSE_MARKDOWN}\n"
        response.content = (response.content.decode() + license_md).encode()
        return response
