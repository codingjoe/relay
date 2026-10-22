import datetime

from django.conf import settings
from django.db.models import Count, Max
from django.http import HttpResponse
from django.template import loader
from django.urls import resolve, reverse
from django.utils.cache import (
    patch_cache_control,
    patch_vary_headers,
)
from django.views import generic
from django.views.decorators.http import condition

from abstract.utils import md_2_html, strip_frontmatter

from .content import MarkdownContent

# Publicly cacheable HTML revalidates in the browser after seconds, while the
# shared edge cache shields the origin for a minute. A deploy flushes that
# cache, and an ETag page carries the release in its validator.
PUBLIC_PAGE_CACHE = {
    "public": True,
    "max_age": datetime.timedelta(seconds=5),
    "s_maxage": datetime.timedelta(minutes=1),
    "must_revalidate": True,
}


class CacheControlMixin:
    """Set cache control headers and flag `public` responses for the static chrome."""

    cache_control: dict[str, bool | int | datetime.timedelta] = {}

    def get_cache_directives(self) -> dict[str, bool | int]:
        """Return the cache control directives with durations in whole seconds."""
        return {
            directive: int(value.total_seconds())
            if isinstance(value, datetime.timedelta)
            else value
            for directive, value in self.cache_control.items()
        }

    def dispatch(self, request, *args, **kwargs):
        request.public_cache = "public" in self.cache_control
        response = super().dispatch(request, *args, **kwargs)
        patch_cache_control(response, **self.get_cache_directives())
        return response


class RevalidationCacheMixin(CacheControlMixin):
    """
    Let the browser reuse a revalidating page for a moment.

    `private` keeps the shared edge cache out of it, and `max-age` lets the
    browser serve the page from its own cache before it comes back and
    revalidates against the ETag.
    """

    cache_control = {
        "private": True,
        "max_age": datetime.timedelta(seconds=5),
        "must_revalidate": True,
    }


def get_release_etag(etag: str | None) -> str | None:
    """Return `etag` as a quoted ETag, scoped to the running release."""
    validator = etag.removeprefix("W/").strip('"') if etag else None
    scope = f"{settings.SENTRY_RELEASE}:" if settings.SENTRY_RELEASE else ""
    return f'"{scope}{validator}"' if validator else None


class ConditionalGetMixin(RevalidationCacheMixin):
    """Answer conditional GETs with an ETag and `Last-Modified` from the object."""

    def get_etag(self, obj) -> str:
        """Return the ETag for `obj`."""
        return f'"{int(obj.pk):x}-{int(obj.modified_at.timestamp() * 1e6):x}"'

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        return condition(
            etag_func=lambda request, *a, **kw: get_release_etag(
                self.get_etag(self.object)
            ),
            last_modified_func=lambda request, *a, **kw: self.object.modified_at,
        )(
            lambda request: self.render_to_response(
                self.get_context_data(object=self.object)
            )
        )(request)


class ConditionalGetListMixin(RevalidationCacheMixin):
    """Answer conditional GETs for a list with an ETag and `Last-Modified` from its newest row."""

    def get_list_summary(self, queryset) -> tuple[int, datetime.datetime | None]:
        """Return the number of rows and the newest modification time of the list."""
        summary = queryset.aggregate(
            count=Count("pk"),
            modified_at=Max("modified_at"),
        )
        return summary["count"], summary["modified_at"]

    def get_list_etag(self, count: int, modified_at: datetime.datetime | None) -> str:
        """Return the ETag of the list summary."""
        if modified_at is None:
            return f'"{count:x}"'
        return f'"{count:x}-{int(modified_at.timestamp() * 1e6):x}"'

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        count, modified_at = self.get_list_summary(self.object_list)
        return condition(
            etag_func=lambda request, *a, **kw: get_release_etag(
                self.get_list_etag(count, modified_at)
            ),
            last_modified_func=lambda request, *a, **kw: modified_at,
        )(lambda request: self.render_to_response(self.get_context_data()))(request)


class NoStoreCacheMixin(CacheControlMixin):
    """Prevent caching entirely with `no-store`."""

    cache_control = {"no_store": True}


class BreadcrumbViewMixin:
    """
    Build breadcrumbs by traversing parent references.

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
    cache_control = PUBLIC_PAGE_CACHE

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
        """
        Return the raw Markdown source as a text/markdown response.

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
            "meta_description": "",
            "markdown_template": self.get_markdown_template(),
            "toc_levels": self.toc_levels,
        }


class MarkdownListView(CacheControlMixin, BreadcrumbViewMixin, generic.TemplateView):
    """Display all Markdown articles in a docs directory."""

    cache_control = PUBLIC_PAGE_CACHE
    parent = "home"
    content: type[MarkdownContent]

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": [
                {
                    "slug": slug,
                    "title": metadata["name"],
                    "description": md_2_html(metadata.get("description", "")),
                    "date": metadata.get("date"),
                }
                for slug, metadata in self.content.get_articles()
            ],
        }


class MarkdownArticleDetailView(MarkdownView):
    """Render a single Markdown article from a docs directory."""

    content: type[MarkdownContent]

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs["slug"]
        return cls.content.get_article_metadata(slug)["name"]

    def get_markdown_template(self):
        return f"{self.kwargs['slug']}.md"

    def get_context_data(self, **kwargs):
        metadata = self.content.get_article_metadata(self.kwargs["slug"])
        return super().get_context_data(**kwargs) | {
            "title": metadata["name"],
            "meta_description": metadata.get("description", ""),
        }
