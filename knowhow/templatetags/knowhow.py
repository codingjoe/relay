"""Template tags for the knowhow app."""

from django.template import Library
from django.urls import reverse
from django.utils.safestring import mark_safe

register = Library()


@register.simple_tag
def knowhow_badge(slug, label=None):
    """Render a small info-icon badge that links to a knowhow article.

    The link opens in a new tab (target="_blank") with rel="noopener".

    Args:
        slug: The article slug (for example, "dmarc").
        label: Optional accessible label for the icon. Defaults to the slug.

    Returns:
        An HTML-safe anchor element with a Lucide info icon.
    """
    url = reverse("knowhow:detail", args=[slug])
    aria_label = label or slug
    return mark_safe(
        f'<a href="{url}" target="_blank" rel="noopener" '
        f'class="inline-flex items-center align-middle text-muted-foreground '
        f'hover:text-foreground transition-colors" '
        f'aria-label="{aria_label} — know how">'
        f'<i data-lucide="info" class="size-3.5" aria-hidden="true"></i>'
        f"</a>"
    )
