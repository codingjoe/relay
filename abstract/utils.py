import datetime
import logging
import random

import markdown
from django.utils import timezone
from django.utils.safestring import SafeText, mark_safe
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.md_in_html import MarkdownInHtmlExtension
from markdown.extensions.toc import TocExtension

logger = logging.getLogger(__name__)


def strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter (`---` delimited) from the start of a Markdown document.

    If the document does not start with a frontmatter block, return it unchanged.
    """
    if not text.startswith("---\n"):
        return text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "".join(lines[i + 1 :]).lstrip("\n")
    return text


def future(now=None, min_offset=1, max_offset=999):
    """
    Return random datetime in the near future.

    Args:
        now (datetime.datetime): Date on which to add the random offset.
        min_offset (int): Minimum number of days to add.
        max_offset (int): Maximum number of days to add.

    Returns:
        datetime.datetime: Random date in the future.

    """
    offset = random.randint(min_offset, max_offset)
    return (now or timezone.localtime()) + datetime.timedelta(days=offset)


def past(now=None):
    """
    Return random datetime in the near past.

    Args:
        now (datetime.datetime): Date on which to subtract the random offset.

    Returns:
        datetime.datetime: Random date in the past.

    """
    return (now or timezone.localtime()) - datetime.timedelta(
        days=random.randint(1, 999),
    )


def md_2_html(document: str, baselevel: int = 1) -> SafeText:
    """
    Convert Markdown to HTML as an HTML-safe string.

    Args:
        document: Markdown string.
        baselevel: Base level for the table of contents (default: 1).

    Returns:
        HTML based on the given Markdown value, including syntax-highlighted
        fenced code blocks.

    """
    html = markdown.markdown(
        document,
        extensions=[
            TocExtension(baselevel=baselevel),
            MarkdownInHtmlExtension(),
            "admonition",
            "def_list",
            "nl2br",
            "smarty",
            "tables",
            "footnotes",
            "fenced_code",
            CodeHiliteExtension(css_class="codehilite"),
        ],
        extension_configs={
            "smarty": {"smart_angled_quotes": True},
            "footnotes": {"BACKLINK_TEXT": ""},
        },
    )

    return mark_safe(html)


def md_toc(document: str, depth=None) -> str:
    """
    Return a table of contents for the given Markdown document.

    Args:
        document (str): Markdown string.
        depth (str|int): The depth of which to create the table of contents.
               This can be a number or a range, for example `1-3`.
               Default: 6.
    """
    md = markdown.Markdown(
        extensions=["toc"],
        extension_configs={"toc": {"toc_depth": depth or 6}},
    )
    md.convert(document)
    return mark_safe(md.toc)
