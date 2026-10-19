from django.utils.translation import gettext_lazy as _

from abstract.views import MarkdownArticleDetailView, MarkdownListView

from .content import DocsContent


class DocsListView(MarkdownListView):
    """Display all product documentation articles."""

    template_name = "docs/list.html"
    title = _("Docs")
    content = DocsContent


class DocsDetailView(MarkdownArticleDetailView):
    """Render a single product documentation article."""

    parent = "docs:list"
    content = DocsContent
