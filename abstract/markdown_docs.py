"""Markdown article parsing and listing for know-how and alternative-to.

Apps that serve Markdown articles from a docs directory (know-how,
alternative-to) share the same frontmatter parsing, title extraction, and
article-listing logic. These functions are parameterized by the docs directory
so each app can reuse them without duplication.
"""

import pathlib

import frontmatter
from django.http import Http404

from abstract.utils import md_2_html, strip_frontmatter


def extract_title(markdown_text: str) -> str:
    """Return the first H1 heading text from the given Markdown."""
    return next(
        (
            line[2:].strip()
            for line in strip_frontmatter(markdown_text).splitlines()
            if line.startswith("# ")
        ),
        "",
    )


def article_slugs(docs_dir: pathlib.Path) -> frozenset[str]:
    """Return a frozenset of article slugs in the given docs directory."""
    return frozenset(p.stem for p in docs_dir.glob("*.md"))


def list_articles(docs_dir: pathlib.Path) -> list[dict[str, str]]:
    """Return all articles in the docs directory with slug, title, and description."""
    return [
        {
            "slug": slug,
            "title": title,
            "description": md_2_html(metadata.get("description", "")),
        }
        for slug in sorted(article_slugs(docs_dir))
        for metadata, text in [frontmatter.parse((docs_dir / f"{slug}.md").read_text())]
        if (title := metadata.get("name") or extract_title(text))
    ]


def article_path(docs_dir: pathlib.Path, slug: str) -> pathlib.Path:
    """Resolve the filesystem path for an article or raise Http404."""
    if slug not in article_slugs(docs_dir):
        raise Http404("Article not found")
    return docs_dir / f"{slug}.md"


def article_title(docs_dir: pathlib.Path, slug: str) -> str:
    """Return the display title (frontmatter name or first H1) for an article."""
    path = article_path(docs_dir, slug)
    text = path.read_text()
    metadata, _ = frontmatter.parse(text)
    return metadata.get("name") or extract_title(text)
