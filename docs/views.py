import pathlib

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from abstract.views import MarkdownArticleDetailView, MarkdownListView

DOCS_DIR = pathlib.Path(settings.BASE_DIR) / "docs" / "docs"
SLUGS = frozenset(p.stem for p in DOCS_DIR.glob("*.md"))


class DocsListView(MarkdownListView):
    """Display all product documentation articles."""

    template_name = "docs/list.html"
    title = _("Docs")
    docs_dir = DOCS_DIR
    slugs = SLUGS


class DocsDetailView(MarkdownArticleDetailView):
    """Render a single product documentation article."""

    parent = "docs:list"
    docs_dir = DOCS_DIR
    slugs = SLUGS
