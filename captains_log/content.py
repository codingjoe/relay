"""Station log product update index, independent of Django views."""

import datetime
import pathlib

import frontmatter
from django.conf import settings
from django.template import engines
from django.utils.safestring import mark_safe

from abstract.content import MarkdownContent
from abstract.utils import md_2_html

CAPTAINS_LOG_DIR = pathlib.Path(settings.BASE_DIR) / "product" / "updates"
SLUGS = frozenset(path.stem for path in CAPTAINS_LOG_DIR.glob("*.md"))


def publication_date(metadata: dict) -> datetime.date:
    """Return the frontmatter date as a date, or the oldest date when missing."""
    value = metadata.get("date")
    match value:
        case datetime.datetime():
            return value.date()
        case datetime.date():
            return value
        case _:
            return datetime.date.min


class CaptainsLogContent(MarkdownContent):
    """Index the product updates in `product/updates`, newest first."""

    docs_dir = CAPTAINS_LOG_DIR
    slugs = SLUGS

    @classmethod
    def get_articles(cls):
        """Yield `(slug, metadata)` from the newest update to the oldest."""
        articles = list(super().get_articles())
        articles.sort(key=lambda article: publication_date(article[1]), reverse=True)
        yield from articles

    @classmethod
    def get_article(cls, slug: str) -> frontmatter.Post:
        """Return the parsed article of one update."""
        return frontmatter.load(cls.get_article_path(slug))

    @classmethod
    def render_body(
        cls,
        slug: str,
        *,
        image_width: int | None = None,
    ) -> str:
        """Return the update body as HTML, rendering its template tags first."""
        source = cls.get_article(slug).content
        body = engines["django"].from_string(source).render({})
        html = str(md_2_html(body, line_breaks=False))
        if image_width is not None:
            html = html.replace("<img ", f'<img width="{image_width}" ')
        # md_2_html escapes the Markdown source before it returns the markup.
        return mark_safe(html)  # noqa: S308
