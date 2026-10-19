"""Expose the know-how articles to MCP clients."""

from django.http import Http404
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.resources import resource

from abstract.mcp import render_markdown_template

from .views import LICENSE_MARKDOWN, KnowHowDetailView, KnowHowListView


class KnowHowArticleError(ResourceError):
    """Signal a know-how slug relay does not serve."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Know-how article not found: {slug}")


def get_know_how_article(slug: str) -> str:
    """
    Return one know-how article as Markdown.

    Args:
        slug: Article slug from the know-how index.

    """
    try:
        KnowHowDetailView.get_article_path(slug)
    except Http404 as error:
        raise KnowHowArticleError(slug) from error
    return f"{render_markdown_template(f'{slug}.md')}\n\n---\n\n{LICENSE_MARKDOWN}"


def register_know_how_resources(mcp: FastMCP) -> None:
    """Register one resource for each know-how article."""
    for slug, metadata in KnowHowListView.get_articles():
        uri = f"know-how://{slug}"
        mcp.add_resource(know_how_resource(uri=uri, slug=slug, metadata=metadata))


def know_how_resource(uri: str, slug: str, metadata: dict[str, object]):
    """Build a resource object for one know-how article."""

    @resource(
        uri,
        mime_type="text/markdown",
        name=f"know-how-{slug}",
        title=metadata["name"],
        description=metadata.get("description", ""),
    )
    def reader() -> str:
        return get_know_how_article(slug)

    return reader
