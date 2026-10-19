"""Expose the know-how articles to MCP clients."""

from django.http import Http404
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from fastmcp.resources.types import TextResource

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
    """Register one text resource for each know-how article."""
    for slug, metadata in KnowHowListView.get_articles():
        mcp.add_resource(
            TextResource(
                uri=f"know-how://{slug}",
                name=f"know-how-{slug}",
                title=metadata["name"],
                description=metadata.get("description", ""),
                mime_type="text/markdown",
                text=get_know_how_article(slug),
            )
        )
