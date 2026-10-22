"""Captain's log product update index, independent of Django views."""

import datetime
import pathlib

from django.conf import settings

from abstract.content import MarkdownContent

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
