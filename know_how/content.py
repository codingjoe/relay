"""Know-how article index, independent of Django views."""

import pathlib

from django.conf import settings

from abstract.content import MarkdownContent

KNOW_HOW_DIR = pathlib.Path(settings.BASE_DIR) / "know_how" / "docs"
SLUGS = frozenset(p.stem for p in KNOW_HOW_DIR.glob("*.md"))

LICENSE_MARKDOWN = (
    "This work is licensed under a "
    "[Creative Commons Attribution-ShareAlike 4.0 International License]"
    "(https://creativecommons.org/licenses/by-sa/4.0/)."
)

LICENSE_YAML = "CC-BY-SA-4.0"


class KnowHowContent(MarkdownContent):
    docs_dir = KNOW_HOW_DIR
    slugs = SLUGS
