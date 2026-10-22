from django.http import HttpResponse
from django.templatetags.static import static
from django.utils.translation import gettext_lazy as _

from abstract.utils import md_2_html, md_toc
from abstract.views import MarkdownListView, MarkdownView

from .content import CaptainsLogContent


class CaptainsLogListView(MarkdownListView):
    """Display every station log update, newest first."""

    template_name = "captains_log/list.html"
    title = _("Station log")
    content = CaptainsLogContent

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "articles": [
                {
                    "slug": slug,
                    "title": metadata["name"],
                    "description": md_2_html(metadata.get("description", "")),
                    "date": metadata["date"],
                }
                for slug, metadata in self.content.get_articles()
            ],
        }


class CaptainsLogDetailView(MarkdownView):
    """Render one station log update."""

    template_name = "captains_log/detail.html"
    parent = "captains_log:list"
    content = CaptainsLogContent

    @classmethod
    def get_title(cls, request):
        slug = request.resolver_match.kwargs["slug"]
        return cls.content.get_article_metadata(slug)["name"]

    def get_article(self):
        return self.content.get_article(self.kwargs["slug"])

    def get_context_data(self, **kwargs):
        article = self.get_article()
        metadata = article.metadata
        slug = self.kwargs["slug"]
        image = str(metadata.get("image", ""))
        og_image = self.request.build_absolute_uri(static(image)) if image else ""
        return super().get_context_data(**kwargs) | {
            "title": metadata["name"],
            "meta_description": metadata.get("description", ""),
            "date": metadata["date"],
            "author": metadata.get("author", ""),
            "og_image": og_image,
            "content_html": self.content.render_body(slug),
            "toc_html": md_toc(article.content, depth=self.toc_levels),
        }

    def render_markdown(self, request, **kwargs):
        return HttpResponse(
            self.get_article().content,
            content_type="text/markdown; charset=utf-8",
        )
