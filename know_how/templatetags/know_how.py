"""Template tags for the know_how app."""

from django.template import Library
from django.urls import reverse

register = Library()


@register.inclusion_tag("know_how/badge.html")
def know_how_badge(slug, label=None):
    """Render a small info-icon badge that links to a know_how article.

    The link opens in a new tab (target="_blank") with rel="noopener".

    Args:
        slug: The article slug (for example, "dmarc").
        label: Optional accessible label for the icon. Defaults to the slug.
    """
    return {
        "url": reverse("know_how:detail", args=[slug]),
        "aria_label": label or slug,
    }
