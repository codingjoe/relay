"""Product documentation article index, independent of Django views."""

import pathlib

from django.conf import settings

from abstract.content import MarkdownContent

DOCS_DIR = pathlib.Path(settings.BASE_DIR) / "docs" / "docs"
SLUGS = frozenset(p.stem for p in DOCS_DIR.glob("*.md"))


class DocsContent(MarkdownContent):
    docs_dir = DOCS_DIR
    slugs = SLUGS
