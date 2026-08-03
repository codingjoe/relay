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
    # `docs_dir` is a module-level constant derived from `settings.BASE_DIR`,
    # never user input, so path access cannot escape the project tree.
    if not docs_dir.exists():  # codeql[py/path-injection]
        return frozenset()
    return frozenset(p.stem for p in docs_dir.glob("*.md"))  # codeql[py/path-injection]


def list_articles(docs_dir):
    """Return all articles in the docs directory with slug, title, and description."""
    docs_dir = pathlib.Path(docs_dir)
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


def article_path(docs_dir, slug):
    """Resolve the filesystem path for an article or raise Http404."""
    docs_dir = pathlib.Path(docs_dir)
    if slug not in article_slugs(docs_dir):
        raise Http404("Article not found")
    return docs_dir / f"{slug}.md"


def article_title(docs_dir, slug):
    """Return the display title (frontmatter name or first H1) for an article."""
    # `slug` was just validated against `article_slugs(docs_dir)`, whose values
    # are filesystem-derived `pathlib.Path.stem` entries, so `path` cannot
    # escape `docs_dir`.
    path = article_path(docs_dir, slug)
    text = path.read_text()  # codeql[py/path-injection]
    metadata, _ = frontmatter.parse(text)
    return metadata.get("name") or extract_title(text)
