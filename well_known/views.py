"""Well-known endpoint views — robots.txt, llms.txt, llms-full.txt, sitemap."""

from django.template import loader
from django.urls import reverse
from django.views.generic import TemplateView

from abstract.utils import strip_frontmatter
from know_how.views import list_articles


class RobotsTxtView(TemplateView):
    """Serve robots.txt with the sitemap URL."""

    template_name = "well_known/robots.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "sitemap_url": self.request.build_absolute_uri(
                reverse("well_known:sitemap")
            ),
        }


class LlmsTxtView(TemplateView):
    """Serve llms.txt following the spec at llmstxt.org."""

    template_name = "well_known/llms.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        articles = [
            {
                "title": article["title"],
                "url": self.request.build_absolute_uri(
                    reverse("know_how:detail", args=[article["slug"]])
                ),
            }
            for article in list_articles()
        ]
        legal_pages = [
            {"title": label, "url": self.request.build_absolute_uri(reverse(name))}
            for name, label in [
                ("legal:imprint", "Imprint"),
                ("legal:terms", "Terms of Service"),
                ("legal:privacy", "Privacy Policy"),
            ]
        ]
        return super().get_context_data(**kwargs) | {
            "articles": articles,
            "legal_pages": legal_pages,
        }


class LlmsFullTxtView(TemplateView):
    """Serve llms-full.txt with the full content of all know-how articles."""

    template_name = "well_known/llms-full.txt"
    content_type = "text/plain; charset=utf-8"

    def get_context_data(self, **kwargs):
        articles = [
            {
                "title": article["title"],
                "url": self.request.build_absolute_uri(
                    reverse("know_how:detail", args=[article["slug"]])
                ),
                "content": strip_frontmatter(
                    loader.get_template(f"{article['slug']}.md").render(
                        request=self.request
                    )
                ),
            }
            for article in list_articles()
        ]
        return super().get_context_data(**kwargs) | {
            "articles": articles,
        }
