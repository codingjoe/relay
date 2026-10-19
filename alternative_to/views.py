from django.utils.translation import gettext_lazy as _

from abstract.views import MarkdownArticleDetailView, MarkdownListView

from .content import AlternativeToContent


class AlternativeToListView(MarkdownListView):
    """Display all alternative-to comparison articles."""

    template_name = "alternative_to/list.html"
    title = _("Alternative to")
    content = AlternativeToContent


class AlternativeToDetailView(MarkdownArticleDetailView):
    """Render a single alternative-to comparison article."""

    parent = "alternative_to:list"
    content = AlternativeToContent
