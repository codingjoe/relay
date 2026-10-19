"""Expose the know-how articles to MCP clients."""

from django.template import Context, Engine
from fastmcp import FastMCP
from fastmcp.resources.types import TextResource

from abstract.utils import strip_frontmatter

from .content import KNOW_HOW_DIR, LICENSE_MARKDOWN, KnowHowContent

TEMPLATE_ENGINE = Engine(dirs=[KNOW_HOW_DIR])


def get_know_how_article(slug: str) -> str:
    """Render the know-how article with the given slug as Markdown."""
    text = TEMPLATE_ENGINE.get_template(f"{slug}.md").render(Context({}))
    return f"{strip_frontmatter(text)}\n\n---\n\n{LICENSE_MARKDOWN}"


def register_know_how_resources(mcp: FastMCP) -> None:
    """Expose one text resource per know-how article."""
    for slug, metadata in KnowHowContent.get_articles():
        mcp.add_resource(
            TextResource(
                uri=f"know-how://{slug}",
                name=slug,
                title=metadata["name"],
                description=metadata.get("description", ""),
                mime_type="text/markdown",
                text=get_know_how_article(slug),
            )
        )
