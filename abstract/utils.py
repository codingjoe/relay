import datetime
import logging
import random
import re
from html import escape

import markdown
from django.utils import timezone
from django.utils.safestring import SafeText, mark_safe
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.md_in_html import MarkdownInHtmlExtension
from markdown.extensions.toc import TocExtension
from markdown.preprocessors import Preprocessor

logger = logging.getLogger(__name__)

MERMAID_FENCE = re.compile(r"^(```|~~~)mermaid[ \t]*$")
FENCE_END = re.compile(r"^(```|~~~)[ \t]*$")


class MermaidPreprocessor(Preprocessor):
    """
    Convert fenced ```mermaid blocks into raw HTML Mermaid targets.

    Runs before the fenced_code preprocessor, which would otherwise
    highlight the diagram source as code.
    """

    def run(self, lines):
        output = []
        content: list[str] = []
        inside = False
        for line in lines:
            if not inside:
                if MERMAID_FENCE.match(line):
                    inside = True
                    content = []
                else:
                    output.append(line)
            elif FENCE_END.match(line):
                inside = False
                code = escape("\n".join(content).strip("\n"))
                # Emit raw HTML on its own line. The html_block preprocessor
                # stashes and restores it.
                output.append(f'<pre class="mermaid">{code}</pre>')
            else:
                content.append(line)
        if inside:
            # Unterminated fence. Restore the opening fence for other handlers.
            output.append("```mermaid")
            output.extend(content)
        return output


class MermaidExtension(markdown.Extension):
    """Render fenced ```mermaid blocks as diagrams with the Mermaid runtime."""

    def extendMarkdown(self, md):
        md.preprocessors.register(MermaidPreprocessor(md), "mermaid", 31)


def strip_frontmatter(text: str) -> str:
    """
    Strip YAML frontmatter (`---` delimited) from the start of a Markdown document.

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
            MermaidExtension(),
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
