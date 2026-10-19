"""Markdown article indexing that does not depend on Django views."""

import pathlib

import frontmatter
from django.http import Http404


class MarkdownContent:
    """
    Content index for Markdown articles served from a docs directory.

    Subclasses set `docs_dir` and the fixed `slugs` index.
    """

    docs_dir: pathlib.Path
    slugs: frozenset[str]

    @classmethod
    def get_articles(cls):
        """Yield `(slug, metadata)` for each article in the fixed index."""
        for slug in sorted(cls.slugs):
            yield slug, frontmatter.load(cls.docs_dir / f"{slug}.md").metadata

    @classmethod
    def get_article_path(cls, slug: str) -> pathlib.Path:
        """Return the indexed file, or raise `Http404` for an unknown slug."""
        if slug in cls.slugs:
            return cls.docs_dir / f"{slug}.md"
        raise Http404

    @classmethod
    def get_article_metadata(cls, slug: str) -> dict[str, str]:
        return frontmatter.load(cls.get_article_path(slug)).metadata
