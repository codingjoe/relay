"""Template tags for the know_how app."""

from django.template import Library
from django.urls import reverse

register = Library()


@register.inclusion_tag("know_how/badge.html")
def know_how_badge(slug, label=None):
    """Render an info-icon badge linking to a know-how article."""
    return {
        "url": reverse("know_how:detail", args=[slug]),
        "aria_label": label or slug,
    }
