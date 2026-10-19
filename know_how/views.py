import frontmatter
from django.http import HttpResponse
from django.template import loader
from django.utils.translation import gettext_lazy as _

from abstract.utils import md_2_html
from abstract.views import MarkdownArticleDetailView, MarkdownListView

from .content import LICENSE_MARKDOWN, LICENSE_YAML, KnowHowContent


class KnowHowListView(MarkdownListView):
    """Display all know-how articles."""

    template_name = "know_how/list.html"
    title = _("Know how")
    content = KnowHowContent

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "license": md_2_html(LICENSE_MARKDOWN),
        }


class KnowHowDetailView(MarkdownArticleDetailView):
    """Render a single know-how article."""

    parent = "know_how:list"
    content = KnowHowContent

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "license": md_2_html(LICENSE_MARKDOWN),
        }

    def render_markdown(self, request, **kwargs):
        """Return the article as text/markdown with license injected into frontmatter."""
        context = self.get_context_data(**kwargs)
        markdown_text = loader.get_template(self.get_markdown_template()).render(
            context=context, request=request
        )
        metadata, content = frontmatter.parse(markdown_text)
        metadata["license"] = LICENSE_YAML
        return HttpResponse(
            frontmatter.dumps(frontmatter.Post(content, **metadata)),
            content_type="text/markdown; charset=utf-8",
        )
