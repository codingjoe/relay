"""Expose the product documentation to MCP clients."""

from django.http import Http404
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.resources import resource

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


def docs_resource(uri: str, slug: str, metadata: dict[str, object]):
    """Build a resource object for one documentation article."""

    @resource(
        uri,
        mime_type="text/markdown",
        name=f"docs-{slug}",
        title=metadata["name"],
        description=metadata.get("description", ""),
    )
    def reader() -> str:
        return get_docs_article(slug)

    return reader


def register_docs_resources(mcp: FastMCP) -> None:
    """Register one resource for each documentation article."""
    for slug, metadata in DocsListView.get_articles():
        uri = f"docs://{slug}"
        mcp.add_resource(docs_resource(uri=uri, slug=slug, metadata=metadata))
