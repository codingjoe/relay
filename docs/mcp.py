"""Expose the product documentation to MCP clients."""

from django.template import Context, Engine
from fastmcp.resources.types import TextResource
from fastmcp.server.providers import LocalProvider

from abstract.utils import strip_frontmatter

from .content import DOCS_DIR, DocsContent

TEMPLATE_ENGINE = Engine(dirs=[DOCS_DIR])


def get_docs_article(slug: str) -> str:
    """Render the documentation article with the given slug as Markdown."""
    text = TEMPLATE_ENGINE.get_template(f"{slug}.md").render(Context({}))
    return strip_frontmatter(text)


def register_components(provider: LocalProvider) -> None:
    """Expose one text resource per documentation article."""
    for slug, metadata in DocsContent.get_articles():
        provider.add_resource(
            TextResource(
                uri=f"docs://{slug}",
                name=slug,
                title=metadata["name"],
                description=metadata.get("description", ""),
                mime_type="text/markdown",
                text=get_docs_article(slug),
            )
        )
