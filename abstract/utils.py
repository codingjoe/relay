import logging
import re
from html import escape

import frontmatter
import markdown
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
    Return the Markdown document without its YAML frontmatter.

    Documents without a frontmatter block return unchanged.
    """
    return frontmatter.parse(text)[1]


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
