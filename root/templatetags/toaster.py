"""Template tags for rendering Django messages as basecoat toasts."""

from django import template
from django.contrib.messages import get_messages

register = template.Library()


@register.simple_tag(takes_context=True)
def render_toasts(context):
    """Render all framework messages as basecoat toast markup.

    Uses ``get_messages`` to read messages directly from the request, avoiding
    any name collision with a view that exposes a queryset as ``context['messages']``.
    Returns an empty string when there are no messages to keep the DOM quiet.
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
    if not toasts:
        return ""
    return template.loader.render_to_string(
        "partials/toaster_items.html",
        {"toasts": toasts},
    )
