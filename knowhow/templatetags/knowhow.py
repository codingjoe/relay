"""Template tags for the knowhow app."""

from django.template import Library
from django.urls import reverse

register = Library()


@register.inclusion_tag("knowhow/badge.html")
def knowhow_badge(slug, label=None):
    """Render a small info-icon badge that links to a knowhow article.

    The link opens in a new tab (target="_blank") with rel="noopener".

    Args:
        slug: The article slug (for example, "dmarc").
        label: Optional accessible label for the icon. Defaults to the slug.
    """
    return {
        "url": reverse("knowhow:detail", args=[slug]),
        "aria_label": label or slug,
    }
