"""Expose the product documentation to MCP clients."""

from django.http import Http404
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.resources.types import TextResource

from abstract.mcp import render_markdown_template

from .views import DocsDetailView, DocsListView


class DocsArticleError(ResourceError):
    """Signal a documentation slug relay does not serve."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Documentation article not found: {slug}")


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


def register_docs_resources(mcp: FastMCP) -> None:
    """Register one text resource for each documentation article."""
    for slug, metadata in DocsListView.get_articles():
        mcp.add_resource(
            TextResource(
                uri=f"docs://{slug}",
                name=f"docs-{slug}",
                title=metadata["name"],
                description=metadata.get("description", ""),
                mime_type="text/markdown",
                text=get_docs_article(slug),
            )
        )
