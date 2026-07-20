from django.urls import reverse
from django.views import generic


class MarkdownView(generic.TemplateView):
    """Render Markdown files in a template."""

    template_name = "abstract/markdown.html"

    title: str = ""
    """Page title."""
    markdown_template: str = ""
    """Template name of the markdown file to render."""
    breadcrumbs: list[tuple[str, str]] = []
    """List of breadcrumbs to render on the page."""
    toc_levels: str = "2-3"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "title": self.title,
            "markdown_template": self.markdown_template,
            "toc_levels": self.toc_levels,
            "breadcrumb_trail": [
                {"label": label, "url": reverse(url) if url else None}
                for label, url in self.breadcrumbs
            ]
            + [{"label": self.title, "url": None}],
        }
