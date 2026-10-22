"""Station log product update index, independent of Django views."""

import pathlib

import frontmatter
from django.conf import settings
from django.template import engines

from abstract.content import MarkdownContent
from abstract.utils import md_2_html

CAPTAINS_LOG_DIR = pathlib.Path(settings.BASE_DIR) / "product" / "updates"
SLUGS = frozenset(path.stem for path in CAPTAINS_LOG_DIR.glob("*.md"))


class CaptainsLogContent(MarkdownContent):
    """Index the product updates in `product/updates`, newest first."""

    docs_dir = CAPTAINS_LOG_DIR
    slugs = SLUGS

    @classmethod
    def get_articles(cls):
        """Yield `(slug, metadata)` from the newest update to the oldest."""
        articles = list(super().get_articles())
        articles.sort(key=lambda article: article[1]["date"], reverse=True)
        yield from articles

    @classmethod
    def get_article(cls, slug: str) -> frontmatter.Post:
        """Return the parsed article of one update."""
        return frontmatter.load(cls.get_article_path(slug))

    @classmethod
    def render_body(cls, slug: str) -> str:
        """Return the update body as HTML, rendering its template tags first."""
        source = cls.get_article(slug).content
        body = engines["django"].from_string(source).render({})
        return md_2_html(body, line_breaks=False)
