import pathlib

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from abstract.views import MarkdownArticleDetailView, MarkdownListView

ALTERNATIVE_TO_DIR = pathlib.Path(settings.BASE_DIR) / "alternative_to" / "docs"
SLUGS = frozenset(p.stem for p in ALTERNATIVE_TO_DIR.glob("*.md"))


class AlternativeToListView(MarkdownListView):
    """Display all alternative-to comparison articles."""

    template_name = "alternative_to/list.html"
    title = _("Alternative to")
    docs_dir = ALTERNATIVE_TO_DIR
    slugs = SLUGS


class AlternativeToDetailView(MarkdownArticleDetailView):
    """Render a single alternative-to comparison article."""

    parent = "alternative_to:list"
    docs_dir = ALTERNATIVE_TO_DIR
    slugs = SLUGS
