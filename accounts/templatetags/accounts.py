import hashlib

from django import template
from django.conf import settings
from django.contrib.auth.models import User

register = template.Library()


@register.simple_tag
def gravatar_url(user: User, size: int = 80) -> str:
    """
    Return the Gravatar URL for the given user.

    If the user has no email or no registered Gravatar, the function returns
    an `identicon` URL instead. The URL uses HTTPS.

    Args:
        user: The user whose Gravatar URL to return.
        size: The image size in pixels.

    Returns:
        The Gravatar URL string.

    """
    email = (getattr(user, "email", "") or "").strip().lower()
    digest = hashlib.md5(email.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"


@register.simple_tag
def platform_name() -> str:
    """Return the configured site name used in templates."""
    return getattr(settings, "RELAY_PLATFORM_NAME", "relay")
