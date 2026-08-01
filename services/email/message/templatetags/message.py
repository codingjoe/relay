"""Contact-timeline link tags and email syntax highlighting."""

import urllib.parse

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.email import EmailLexer

register = template.Library()

_FILTER_VIEWS = {
    "email": "message:contact-messages",
    "domain": "message:contact-messages",
    "ip": "dashboard:contact-reports",
}


def _contact_url(view: str, org_slug: str, params: dict[str, str]) -> str:
    base = reverse(view, kwargs={"org_slug": org_slug})
    return f"{base}?{urllib.parse.urlencode(params)}"


def _org_slug_from_context(context) -> str:
    org = context.get("current_org")
    if org is None:
        raise ValueError(
            "contact_link requires current_org in the template context. "
            "Ensure the view extends OrganizationScopedView."
        )
    return org.slug


@register.inclusion_tag("message/link.html", takes_context=True)
def contact_link(context, **filters) -> dict:
    """Render a link to the contact-timeline view with the given filter pairs."""
    if not filters:
        return {"url": "", "value": ""}
    key, value = next(iter(filters.items()))
    if not value:
        return {"url": "", "value": ""}
    view = _FILTER_VIEWS.get(key)
    if view is None:
        raise ValueError(
            f"contact_link: unknown filter key {key!r}. "
            f"Expected one of: {', '.join(sorted(_FILTER_VIEWS))}."
        )
    org_slug = _org_slug_from_context(context)
    return {
        "url": _contact_url(view, org_slug, {key: value}),
        "value": value,
    }


@register.inclusion_tag("message/email_links.html", takes_context=True)
def email_links(context, value: str) -> dict:
    """Turn a comma-separated email field into one link per address."""
    if not value:
        return {"addresses": [], "org_slug": _org_slug_from_context(context)}
    addresses = [addr.strip() for addr in value.split(",") if addr.strip()]
    return {
        "addresses": addresses,
        "org_slug": _org_slug_from_context(context),
    }


@register.inclusion_tag("message/timestamp.html")
def timestamp(value) -> dict:
    """Render a ``<time>`` element with naturaltime and ISO 8601 tooltip."""
    from django.contrib.humanize.templatetags.humanize import naturaltime

    if not value:
        return {"value": None, "iso": "", "natural": ""}
    return {
        "value": value,
        "iso": value.isoformat(),
        "natural": naturaltime(value),
    }


_email_formatter = HtmlFormatter(cssclass="highlight-email")


@register.filter
def highlight_email(value: str) -> str:
    """Render a raw RFC 822 message with Pygments' :class:`EmailLexer`."""
    if not value:
        return ""
    return mark_safe(highlight(value, EmailLexer(), _email_formatter))
