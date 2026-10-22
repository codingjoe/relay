from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.utils import md_2_html, md_toc
from abstract.views import MarkdownListView, MarkdownView

from .content import CAPTAINS_LOG_DIR, CaptainsLogContent, publication_date


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
                    "date": publication_date(metadata),
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
        image_base = reverse(
            "captains_log:image",
            kwargs={"slug": slug, "name": "placeholder"},
        ).removesuffix("placeholder")
        image = str(metadata.get("image", "")).removeprefix("images/")
        og_image = (
            self.request.build_absolute_uri(
                reverse(
                    "captains_log:image",
                    kwargs={"slug": slug, "name": image},
                )
            )
            if image
            else ""
        )
        return super().get_context_data(**kwargs) | {
            "title": metadata["name"],
            "meta_description": metadata.get("description", ""),
            "date": publication_date(metadata),
            "author": metadata.get("author", ""),
            "og_image": og_image,
            "content_html": self.content.render_body(slug, image_base),
            "toc_html": md_toc(article.content, depth=self.toc_levels),
        }

    def render_markdown(self, request, **kwargs):
        return HttpResponse(
            self.get_article().content,
            content_type="text/markdown; charset=utf-8",
        )


class CaptainsLogImageView(generic.View):
    """Serve a screenshot that belongs to one station log update."""

    def get(self, request, slug, name, *args, **kwargs):
        if slug not in CaptainsLogContent.slugs:
            raise Http404
        image_root = (CAPTAINS_LOG_DIR / "images").resolve()
        image_path = (image_root / name).resolve()
        if (
            not image_path.is_relative_to(image_root)
            or image_path.suffix != ".png"
            or not image_path.is_file()
        ):
            raise Http404
        response = FileResponse(image_path.open("rb"), content_type="image/png")
        response["Cache-Control"] = f"public, max-age={settings.SERVESTATIC_MAX_AGE}"
        return response
