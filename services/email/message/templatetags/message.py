"""Contact-timeline link tags and email syntax highlighting."""

import ipaddress
import re
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

_DOMAIN_RE = re.compile(
    r"(?<![\w@.])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,}(?![\w.])",
    re.IGNORECASE,
)


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


def _find_entities(text: str) -> list[tuple[int, int, str, str]]:
    """Return (start, end, kind, value) tuples for every recognized entity.

    ``kind`` is one of ``email``, ``ip``, ``domain``. ``value`` is the
    matched substring. Positions are non-overlapping and sorted.
    """
    matches: list[tuple[int, int, str, str]] = []

    for match in re.finditer(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", text):
        try:
            if validators.email(match.group()):
                matches.append((match.start(), match.end(), "email", match.group()))
        except validators.ValidationError:
            continue

    for match in re.finditer(r"\b[0-9A-Fa-f:.]+\b", text):
        try:
            ipaddress.ip_address(match.group())
        except ValueError:
            continue
        matches.append((match.start(), match.end(), "ip", match.group()))

    for match in _DOMAIN_RE.finditer(text):
        matches.append((match.start(), match.end(), "domain", match.group()))

    matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))
    filtered: list[tuple[int, int, str, str]] = []
    for m in matches:
        if filtered and m[0] < filtered[-1][1]:
            continue
        filtered.append(m)
    return filtered


@register.inclusion_tag("message/header_value.html", takes_context=True)
def header_value(context, value: str) -> dict:
    """Render a header value with emails, IPs, and domains as links.

    Text that does not match a known entity (e.g. a header name body,
    free-form prose) is rendered as plain text. Only entities that
    validate are linked — emails must be valid, IPs must parse, and
    domains must have at least one dot.
    """
    if not value:
        return {"spans": []}
    org_slug = _org_slug_from_context(context)
    spans: list[dict[str, str]] = []
    cursor = 0
    for start, end, kind, matched in _find_entities(value):
        if start > cursor:
            spans.append({"text": value[cursor:start], "url": ""})
        view = _FILTER_VIEWS[kind]
        spans.append(
            {
                "text": matched,
                "url": _contact_url(view, org_slug, {kind: matched}),
            }
        )
        cursor = end
    if cursor < len(value):
        spans.append({"text": value[cursor:], "url": ""})
    return {"spans": spans}


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


@register.filter
def get_status_label(status, choices):
    """Return the human label for ``status`` from a ``(value, label)`` iterable."""
    if not status or not choices:
        return ""
    for value, label in choices:
        if value == status:
            return label
    return status
