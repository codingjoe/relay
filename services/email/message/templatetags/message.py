"""Contact-timeline link tags and email syntax highlighting."""

import urllib.parse

import validators
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


_ADDRESS_HEADERS = frozenset(
    h.lower()
    for h in (
        "from",
        "to",
        "cc",
        "bcc",
        "reply-to",
        "sender",
        "return-path",
        "resent-from",
        "resent-to",
        "resent-cc",
        "resent-bcc",
    )
)


@register.inclusion_tag("message/header_value.html", takes_context=True)
def header_value(context, key: str, value: str) -> dict:
    """Render a header value, linking email addresses when the header carries them.

    Address-bearing headers (From, To, Cc, Bcc, Reply-To, Sender, Return-Path,
    and the Resent-* variants) are split on commas and each candidate is
    validated with the ``validators`` package before being linked. Every other
    header is rendered as plain text.
    """
    if not value:
        return {"spans": []}
    if key.lower() in _ADDRESS_HEADERS:
        return _address_spans(context, value)
    return {"spans": [{"text": value, "url": ""}]}


def _address_spans(context, value: str) -> dict:
    """Split an address header value into text and validated email spans."""
    org_slug = _org_slug_from_context(context)
    spans: list[dict[str, str]] = []
    chunks = value.split(",")
    for index, chunk in enumerate(chunks):
        if index > 0:
            spans.append({"text": ",", "url": ""})
        address = chunk.strip()
        spans.append(
            {
                "text": address,
                "url": _contact_url(
                    "message:contact-messages",
                    org_slug,
                    {"email": address},
                )
                if address and _is_valid_email(address)
                else "",
            }
        )
    return {"spans": spans}


def _is_valid_email(address: str) -> bool:
    """Return whether ``address`` validates as an email via the ``validators`` package."""
    try:
        return bool(validators.email(address))
    except validators.ValidationError:
        return False


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


@register.filter
def get_item(mapping, key):
    """Look up ``key`` in ``mapping``, returning ``""`` when missing."""
    if not mapping:
        return ""
    try:
        return mapping[key]
    except KeyError, TypeError:
        return ""
