"""Expose the product documentation to MCP clients."""

from django.http import Http404
from django.urls import reverse
from fastmcp.exceptions import ResourceError
from fastmcp.resources import resource
from fastmcp.tools import tool

from abstract.mcp import render_markdown_template

from .views import DocsDetailView, DocsListView


class DocsArticleError(ResourceError):
    """Signal a documentation slug relay does not serve."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Documentation article not found: {slug}")


@tool
def list_docs() -> list[dict[str, object]]:
    """
    Return the product documentation index.

    Each entry names its slug and the URI to read the article body.
    """
    return [
        {
            "slug": slug,
            "title": metadata["name"],
            "description": metadata.get("description", ""),
            "author": metadata.get("author", ""),
            "uri": f"docs://{slug}",
            "url": reverse("docs:detail", args=[slug]),
        }
        for slug, metadata in DocsListView.get_articles()
    ]


@resource("docs://{slug}", mime_type="text/markdown")
def get_docs_article(slug: str) -> str:
    """
    Return one product documentation article as Markdown.

    Args:
        slug: Article slug from the documentation index.

    """
    try:
        DocsDetailView.get_article_path(slug)
    except Http404 as error:
        raise DocsArticleError(slug) from error
    return render_markdown_template(f"{slug}.md")
