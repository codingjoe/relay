"""Generic helpers for Markdown-document apps.

Apps that serve Markdown articles from a docs directory (know-how,
alternative-to) share the same frontmatter parsing, title extraction, and
article-listing logic. These functions are parameterized by the docs directory
so each app can reuse them without duplication.
"""

import pathlib
import re

from django.http import Http404

from abstract.utils import md_2_html, strip_frontmatter

# Slugs are filesystem stems: letters, digits, hyphens, underscores. Reject
# anything else so `docs_dir / f"{slug}.md"` cannot escape the docs dir.
SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+\Z")


def parse_frontmatter(text):
    """Extract YAML frontmatter and content from a Markdown document."""
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            frontmatter = "".join(lines[1:i])
            content = "".join(lines[i + 1 :]).lstrip("\n")
            metadata = {}
            for fm_line in frontmatter.splitlines():
                if ":" in fm_line:
                    key, value = fm_line.split(":", 1)
                    metadata[key.strip()] = value.strip().strip("\"'")
            return metadata, content
    return {}, text


def extract_title(markdown_text):
    """Return the first H1 heading text from the given Markdown."""
    return next(
        (
            line[2:].strip()
            for line in strip_frontmatter(markdown_text).splitlines()
            if line.startswith("# ")
        ),
        "",
    )


def article_slugs(docs_dir):
    """Return a frozenset of article slugs in the given docs directory."""
    docs_dir = pathlib.Path(docs_dir)
    if not docs_dir.exists():
        return frozenset()
    return frozenset(p.stem for p in docs_dir.glob("*.md"))


def list_articles(docs_dir):
    """Return all articles in the docs directory with slug, title, and description."""
    docs_dir = pathlib.Path(docs_dir)
    articles = []
    for slug in sorted(article_slugs(docs_dir)):
        text = (docs_dir / f"{slug}.md").read_text()
        metadata, _ = parse_frontmatter(text)
        title = metadata.get("name") or extract_title(text)
        if not title:
            continue
        articles.append(
            {
                "slug": slug,
                "title": title,
                "description": md_2_html(metadata.get("description", "")),
            }
        )
    return articles


def article_path(docs_dir, slug):
    """Resolve the filesystem path for an article or raise Http404."""
    docs_dir = pathlib.Path(docs_dir)
    if not SLUG_RE.fullmatch(slug) or slug not in article_slugs(docs_dir):
        raise Http404("Article not found")
    return docs_dir / f"{slug}.md"


def article_title(docs_dir, slug):
    """Return the display title (frontmatter name or first H1) for an article."""
    path = article_path(docs_dir, slug)
    text = path.read_text()
    metadata, _ = parse_frontmatter(text)
    return metadata.get("name") or extract_title(text)
