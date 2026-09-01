"""Template tags for rendering Django messages as basecoat toasts."""

from django import template
from django.contrib.messages import get_messages

register = template.Library()


@register.inclusion_tag("partials/toaster_items.html", takes_context=True)
def render_toasts(context):
    """
    Render all framework messages as basecoat toast markup.

    Uses `get_messages` to read messages directly from the request. This avoids
    a name collision with a view that exposes a queryset as `context['messages']`.
    """
    request = context["request"]
    toasts = [
        {
            "category": m.tags or m.level_tag,
            "title": m.level_tag.capitalize(),
            "body": m.message,
        }
        for m in get_messages(request)
    ]
    return {"toasts": toasts}
