"""Know-how article views — list and detail."""

import pathlib

from django.conf import settings
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html
from abstract.views import BreadcrumbViewMixin, MarkdownView

KNOW_HOW_DIR = pathlib.Path(settings.BASE_DIR) / "know-how"

LICENSE_MARKDOWN = (
    "This work is licensed under a "
    "[Creative Commons Attribution-ShareAlike 4.0 International License]"
    "(https://creativecommons.org/licenses/by-sa/4.0/)."
)


def list_articles():
    """Return a list of articles as dicts with slug and title.

    Each Markdown file in the know-how directory becomes one article.
    The title comes from the first H1 heading in the file.
    """
    articles = []
    if not KNOW_HOW_DIR.exists():
        return articles
    for path in sorted(KNOW_HOW_DIR.glob("*.md")):
        title = extract_title(path.read_text())
        if not title:
            continue
        articles.append({"slug": path.stem, "title": title})
    return articles


def extract_title(markdown_text):
    """Return the text of the first H1 heading in the given Markdown.

    If the Markdown has no H1 heading, return an empty string.
    """
    for line in markdown_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


class KnowHowListView(BreadcrumbViewMixin, generic.TemplateView):
    """List all know-how articles."""

    template_name = "know_how/list.html"
    title = _("know how")
    parent = "home"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": list_articles(),
            "license": md_2_html(LICENSE_MARKDOWN),
        }


class KnowHowMarkdownView(MarkdownView):
    """MarkdownView with a CC-BY-SA 4.0 license notice.

    The license appears in both the rendered HTML page and the raw
    Markdown response (when content negotiation returns text/markdown).
    The license text is not stored in the Markdown source files — it is
    added by the view at render time.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["license"] = md_2_html(LICENSE_MARKDOWN)
        return context

    def render_markdown(self, request, **kwargs):
        response = super().render_markdown(request, **kwargs)
        license_md = f"\n\n---\n\n{LICENSE_MARKDOWN}\n"
        response.content = (response.content.decode() + license_md).encode()
        return response


class KnowHowDetailView(KnowHowMarkdownView):
    """Render a single know-how article by slug."""

    parent = "know_how:list"

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs.get("slug", "")
        path = KNOW_HOW_DIR / f"{slug}.md"
        if path.exists():
            return extract_title(path.read_text())
        return slug

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        slug = self.kwargs["slug"]
        path = KNOW_HOW_DIR / f"{slug}.md"
        if not path.exists():
            raise Http404("Article not found")
        return super().get_context_data(**kwargs) | {
            "markdown_template": f"{slug}.md",
        }
