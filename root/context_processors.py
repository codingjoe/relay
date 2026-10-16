"""Template context processors for the shared layout."""

from django.conf import settings

EXPOSED_SETTINGS = ("DEBUG",)


def settings_context(request):
    """Expose allow-listed settings to templates under their own names."""
    return {name: getattr(settings, name) for name in EXPOSED_SETTINGS}
