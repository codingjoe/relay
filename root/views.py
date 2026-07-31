"""Root project views."""

from django.http import HttpResponse
from django.template import loader
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from abstract.views import BreadcrumbViewMixin
from know_how.views import list_articles


class HomeView(BreadcrumbViewMixin, TemplateView):
    """Marketing landing page for unauthenticated visitors."""

    template_name = "start.html"
    title = _("Home")

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
        }


class RobotsTxtView(View):
    """Serve robots.txt with the sitemap URL."""

    def get(self, request):
        sitemap_url = request.build_absolute_uri(reverse("sitemap"))
        content = f"User-agent: *\nAllow: /\n\nSitemap: {sitemap_url}\n"
        return HttpResponse(content, content_type="text/plain; charset=utf-8")


class LlmsTxtView(View):
    """Serve llms.txt following the spec at llmstxt.org."""

    def get(self, request):
        lines = [
            "# relay",
            "",
            "> B2B SaaS communication platform with a built-in authoritative nameserver.",
            "> Users set NS delegation and DMARC. The nameserver serves MX, SPF, DKIM, and Return-Path automatically.",
            "",
            "## Know how",
            "",
        ]
        for article in list_articles():
            url = request.build_absolute_uri(
                reverse("know_how:detail", args=[article["slug"]])
            )
            lines.append(f"- [{article['title']}]({url})")
        lines += [
            "",
            "## Legal",
            "",
        ]
        for name, label in [
            ("legal:imprint", "Imprint"),
            ("legal:terms", "Terms of Service"),
            ("legal:privacy", "Privacy Policy"),
        ]:
            url = request.build_absolute_uri(reverse(name))
            lines.append(f"- [{label}]({url})")
        return HttpResponse(
            "\n".join(lines) + "\n",
            content_type="text/plain; charset=utf-8",
        )


class LlmsFullTxtView(View):
    """Serve llms-full.txt with the full content of all know-how articles."""

    def get(self, request):
        sections = [
            "# relay — know how (full text)",
            "",
            "> Complete content of all know-how articles for AI agents.",
            "",
        ]
        for article in list_articles():
            url = request.build_absolute_uri(
                reverse("know_how:detail", args=[article["slug"]])
            )
            template = loader.get_template(f"{article['slug']}.md")
            markdown_text = template.render(request=request)
            sections.append(f"---\n\n# {article['title']}\n\nSource: {url}\n")
            sections.append(markdown_text)
            sections.append("")
        return HttpResponse(
            "\n".join(sections),
            content_type="text/plain; charset=utf-8",
        )
