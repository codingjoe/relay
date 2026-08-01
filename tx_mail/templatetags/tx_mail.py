"""Contact-timeline link tags and email syntax highlighting.

``contact_link`` is a single inclusion tag that accepts key-value
filter pairs and renders a link to the merged contact-timeline view.
The org is pulled from the request context (``current_org``), so
call sites no longer pass ``org`` explicitly.

Usage::

    {% contact_link email="user@example.com" %}
    {% contact_link domain="example.com" %}
    {% contact_link ip="192.0.2.1" %}

``email_links`` handles comma-separated address lists.
``header_value`` renders an RFC 5322 header with every entity linked.
``highlight_email`` remains a filter (Pygments output).
"""

import ipaddress
import re
import urllib.parse
from typing import NamedTuple

import validators
from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.email import EmailLexer

register = template.Library()

# Broad patterns to find *candidate* entities in header text.  Each
# candidate is then validated with the ``validators`` package or the
# stdlib ``ipaddress`` module before it is turned into a link.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_DOMAIN_RE = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}\b"
)
# IPv4: dotted quads; IPv6: colon-separated hex groups, optionally
# bracketed (as in Received headers).
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\[?([0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7})\]?")

# Map filter keys to the view name they link to.
_FILTER_VIEWS = {
    "email": "tx_mail:contact-messages",
    "domain": "tx_mail:contact-messages",
    "ip": "tx_mail:contact-reports",
}


def _contact_url(view: str, org_slug: str, params: dict[str, str]) -> str:
    """Return the merged-view URL with the given query parameters."""
    base = reverse(view, kwargs={"org_slug": org_slug})
    return f"{base}?{urllib.parse.urlencode(params)}"


def _org_slug_from_context(context) -> str:
    """Extract the org slug from the template rendering context."""
    org = context.get("current_org")
    if org is None:
        raise ValueError(
            "contact_link requires current_org in the template context. "
            "Ensure the view extends OrganizationScopedView."
        )
    return org.slug


def _is_email(value: str) -> bool:
    return validators.email(value) is True


def _is_domain(value: str) -> bool:
    return validators.domain(value) is True


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


@register.inclusion_tag("tx_mail/link.html", takes_context=True)
def contact_link(context, **filters) -> dict:
    """Render a link to the contact-timeline view with the given filter pairs.

    Accepts exactly one keyword argument whose name is the filter key
    (``email``, ``domain``, or ``ip``) and whose value is the search term::

        {% contact_link email="user@example.com" %}
        {% contact_link domain="example.com" %}
        {% contact_link ip="192.0.2.1" %}
    """
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


@register.inclusion_tag("tx_mail/email_links.html", takes_context=True)
def email_links(context, value: str) -> dict:
    """Turn a comma-separated email field into one link per address."""
    if not value:
        return {"addresses": [], "org_slug": _org_slug_from_context(context)}
    addresses = [addr.strip() for addr in value.split(",") if addr.strip()]
    return {
        "addresses": addresses,
        "org_slug": _org_slug_from_context(context),
    }


class _Hit(NamedTuple):
    start: int
    end: int
    kind: str
    text: str


def _entity_spans(value: str, org_slug: str) -> list[dict]:
    """Parse ``value`` into a list of span dicts for the header_value template.

    Candidate entities are found with broad regexes, then validated
    with ``validators`` (emails, domains) or ``ipaddress`` (IPs) before
    being turned into links.
    """
    hits: list[_Hit] = []

    for m in _EMAIL_RE.finditer(value):
        if _is_email(m.group(0)):
            hits.append(_Hit(m.start(), m.end(), "email", m.group(0)))
    for m in _DOMAIN_RE.finditer(value):
        if any(h.start <= m.start() and m.end() <= h.end for h in hits):
            continue
        if _is_domain(m.group(0)):
            hits.append(_Hit(m.start(), m.end(), "domain", m.group(0)))
    for m in _IPV4_RE.finditer(value):
        if any(h.start <= m.start() and m.end() <= h.end for h in hits):
            continue
        if _is_ip(m.group(0)):
            hits.append(_Hit(m.start(), m.end(), "ip", m.group(0)))
    for m in _IPV6_RE.finditer(value):
        ip_str = m.group(1)
        start = m.start(1)
        end = m.end(1)
        if any(h.start <= start and end <= h.end for h in hits):
            continue
        if _is_ip(ip_str):
            hits.append(_Hit(start, end, "ip", ip_str))

    hits.sort(key=lambda h: (h.start, h.end))
    deduped: list[_Hit] = []
    last_end = -1
    for h in hits:
        if h.start < last_end:
            continue
        deduped.append(h)
        last_end = h.end

    spans: list[dict] = []
    cursor = 0
    for h in deduped:
        if cursor < h.start:
            spans.append({"text": value[cursor : h.start], "url": None})
        view = _FILTER_VIEWS.get(h.kind, "tx_mail:contact-reports")
        url = _contact_url(view, org_slug, {h.kind: h.text})
        spans.append({"text": h.text, "url": url})
        cursor = h.end
    if cursor < len(value):
        spans.append({"text": value[cursor:], "url": None})
    return spans


@register.inclusion_tag("tx_mail/header_value.html", takes_context=True)
def header_value(context, value: str) -> dict:
    """Render an RFC 5322 header value with every entity turned into a link."""
    if not value:
        return {"spans": []}
    return {"spans": _entity_spans(value, _org_slug_from_context(context))}


_email_formatter = HtmlFormatter(cssclass="highlight-email")


@register.filter
def highlight_email(value: str) -> str:
    """Render a raw RFC 822 message with Pygments' :class:`EmailLexer`."""
    if not value:
        return ""
    return mark_safe(highlight(value, EmailLexer(), _email_formatter))
