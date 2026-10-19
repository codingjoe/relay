"""Alternative-to article index, independent of Django views."""

import pathlib

from django.conf import settings

from abstract.content import MarkdownContent

ALTERNATIVE_TO_DIR = pathlib.Path(settings.BASE_DIR) / "alternative_to" / "docs"
SLUGS = frozenset(p.stem for p in ALTERNATIVE_TO_DIR.glob("*.md"))


class AlternativeToContent(MarkdownContent):
    docs_dir = ALTERNATIVE_TO_DIR
    slugs = SLUGS
