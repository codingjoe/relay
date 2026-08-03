import pathlib

import frontmatter
from django.http import Http404, HttpResponse
from django.template import loader
from django.urls import resolve, reverse
from django.utils.cache import patch_cache_control, patch_vary_headers
from django.views import generic

from abstract.utils import strip_frontmatter


class CacheControlMixin:
    """Set cache control headers on the response of a class based view."""

    cache_control: dict[str, bool | int] = {}

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        patch_cache_control(response, **self.cache_control)
        return response


class MarkdownArticleMixin:
    """Mixin for views that serve Markdown articles from a docs directory.

    Subclasses must set:
    - `docs_dir`: pathlib.Path to the docs directory.
    - `slugs`: frozenset of allowed article slugs (filenames without .md).
    """

    docs_dir: pathlib.Path
    slugs: frozenset[str]

    @classmethod
    def get_articles(cls):
        """Yield (slug, metadata) for each article in the docs directory."""
        for slug in sorted(cls.slugs):
            metadata, _ = frontmatter.parse((cls.docs_dir / f"{slug}.md").read_text())
            yield slug, metadata

    @classmethod
    def get_article_path(cls, slug: str) -> pathlib.Path:
        """Resolve the filesystem path for an article or raise Http404."""
        if slug not in cls.slugs:
            raise Http404("Article not found")
        return cls.docs_dir / f"{slug}.md"

    @classmethod
    def get_article_metadata(cls, slug: str) -> dict[str, str]:
        """Return the frontmatter metadata for an article."""
        path = cls.get_article_path(slug)
        text = path.read_text()
        metadata, _ = frontmatter.parse(text)
        return metadata


class BreadcrumbViewMixin:
    """Build breadcrumbs by traversing parent references.

    Each view sets:
    - `title`: the breadcrumb title for this page (class attribute).
    - `parent`: the URL name of the parent page, or "" for the root.

    Override `get_title(cls, request)` for dynamic titles that depend on
    the request (for example, the current org name from `request.current_org`).
    Override `get_url(cls, request)` for URL patterns that need kwargs
    from the request (for example, org-scoped views).
    """

    title: str = ""
    parent: str = ""

    @classmethod
    def get_title(cls, request=None) -> str:
        """Return the breadcrumb title for this page."""
        return str(cls.title) if cls.title else ""

    @classmethod
    def get_url(cls, request) -> str | None:
        """Return the URL for this view's parent, or None if this is the root."""
        if not cls.parent:
            return None
        return reverse(cls.parent)

    def get_breadcrumbs(self):
        """Build the breadcrumb chain by traversing parents to the root."""
        breadcrumbs = [{"title": self.get_title(self.request), "url": None}]
        if not breadcrumbs[0]["title"] and hasattr(self, "object") and self.object:
            breadcrumbs[0]["title"] = str(self.object)

        url = self.get_url(self.request)
        while url:
            match = resolve(url)
            view_class = getattr(match.func, "view_class", None)
            if view_class and hasattr(view_class, "get_title"):
                title = view_class.get_title(self.request)
                breadcrumbs.append({"title": title, "url": url})
                url = view_class.get_url(self.request)
            else:
                breadcrumbs.append({"title": "", "url": url})
                break

        breadcrumbs.reverse()
        return breadcrumbs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "breadcrumbs": self.get_breadcrumbs(),
        }


class MarkdownView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Render Markdown files in a template."""

    template_name = "abstract/markdown.html"

    title: str = ""
    """Page title."""
    markdown_template: str = ""
    """Template name of the markdown file to render."""
    toc_levels: str = "2-3"
    cache_control = {"public": True, "max_age": 3600}

    def get_markdown_template(self):
        """Return the markdown template name for this view."""
        return self.markdown_template

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        patch_vary_headers(response, ["Accept"])
        return response

    def get(self, request, *args, **kwargs):
        if request.GET.get("md") or "text/markdown" in request.headers.get(
            "Accept", ""
        ):
            return self.render_markdown(request, **kwargs)
        return super().get(request, *args, **kwargs)

    async def aget(self, request, *args, **kwargs):
        if request.GET.get("md") or "text/markdown" in request.headers.get(
            "Accept", ""
        ):
            return self.render_markdown(request, **kwargs)
        return await super().aget(request, *args, **kwargs)

    def render_markdown(self, request, **kwargs):
        """Return the raw Markdown source as a text/markdown response.

        Frontmatter is stripped so metadata is not exposed in the raw
        Markdown endpoint of generic views.
        """
        context = self.get_context_data(**kwargs)
        markdown_text = loader.get_template(self.get_markdown_template()).render(
            context=context, request=request
        )
        return HttpResponse(
            strip_frontmatter(markdown_text),
            content_type="text/markdown; charset=utf-8",
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "title": self.title,
            "markdown_template": self.get_markdown_template(),
            "toc_levels": self.toc_levels,
        }
