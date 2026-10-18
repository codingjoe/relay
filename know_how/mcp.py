"""Expose the know-how articles to MCP clients."""

import json

from django.http import Http404
from django.urls import reverse
from fastmcp.exceptions import ResourceError
from fastmcp.resources import resource

from abstract.mcp import render_markdown_template

from .views import LICENSE_MARKDOWN, KnowHowDetailView, KnowHowListView


class KnowHowArticleError(ResourceError):
    """Signal a know-how slug relay does not serve."""

    def __init__(self, slug: str) -> None:
        super().__init__(f"Know-how article not found: {slug}")


@resource("relay://know-how", mime_type="application/json")
def list_know_how() -> str:
    """Return the know-how index."""
    return json.dumps(
        {
            "articles": [
                {
                    "slug": slug,
                    "title": metadata["name"],
                    "description": metadata.get("description", ""),
                    "author": metadata.get("author", ""),
                    "uri": f"relay://know-how/{slug}",
                    "url": reverse("know_how:detail", args=[slug]),
                }
                for slug, metadata in KnowHowListView.get_articles()
            ]
        }
    )


@resource("relay://know-how/{slug}", mime_type="text/markdown")
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
