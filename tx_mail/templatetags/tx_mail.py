"""Filters that turn addresses, domains, and IPs into contact-timeline links."""

import re
import urllib.parse
from typing import NamedTuple

from django.template.defaulttags import register
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.email import EmailLexer

# Match entities that should become links inside an RFC 5322 header value.
# Email first (so the local@host form is not split into a domain-only link),
# then domains, then IPv4, then bracketed-IPv6 (which appears in `Received`
# and `Authentication-Results` headers).
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_DOMAIN_RE = re.compile(
    r"\b(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}\b"
)
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_BRACKETED_IPV6_RE = re.compile(r"\[([0-9A-Fa-f:]+)\]")


def _contact_url(view: str, org_slug: str, params: dict[str, str]) -> str:
    """Return the merged-view URL with the given query parameters."""
    base = reverse(view, kwargs={"org_slug": org_slug})
    return f"{base}?{urllib.parse.urlencode(params)}"


def _org_slug(org) -> str:
    return org if isinstance(org, str) else org.slug


@register.filter
def email_link(value: str, org) -> str:
    """Turn a single email address into a link to the contact-timeline messages view.

    Returns an empty string when empty.
    """
    if not value:
        return ""
    return format_html(
        '<a class="link" href="{}">{}</a>',
        _contact_url("tx_mail:contact-messages", _org_slug(org), {"email": value}),
        value,
    )


@register.filter
def email_links(value: str, org) -> str:
    """Turn a comma-separated email field into one link per address.

    Returns the original value when empty.
    """
    if not value:
        return ""
    addresses = [addr.strip() for addr in value.split(",") if addr.strip()]
    if not addresses:
        return value
    org_slug = _org_slug(org)
    links = format_html_join(
        ", ",
        '<a class="link" href="{}">{}</a>',
        (
            (
                _contact_url("tx_mail:contact-messages", org_slug, {"email": addr}),
                addr,
            )
            for addr in addresses
        ),
    )
    return format_html("{}", links)


@register.filter
def domain_link(value: str, org) -> str:
    """Turn a domain name into a link to the contact-timeline messages view.

    Returns an empty string when empty.
    """
    if not value:
        return ""
    return format_html(
        '<a class="link" href="{}">{}</a>',
        _contact_url("tx_mail:contact-messages", _org_slug(org), {"domain": value}),
        value,
    )


@register.filter
def ip_link(value: str, org) -> str:
    """Turn an IPv4 or IPv6 address into a link to the contact-timeline reports view.

    Returns an empty string when empty.
    """
    if not value:
        return ""
    return format_html(
        '<a class="link" href="{}">{}</a>',
        _contact_url("tx_mail:contact-reports", _org_slug(org), {"ip": value}),
        value,
    )


def _entity_spans(value: str, org_slug: str) -> list[str]:
    """Yield a sequence of safe HTML fragments representing ``value``.

    Each fragment is either escaped plaintext or a SafeString anchor. The
    caller joins them with :func:`format_html`. Email matches are extracted
    first so that ``local@host`` is not double-linked as ``host`` only;
    IPs found inside brackets are extracted as bare IP forms.
    """

    class _Hit(NamedTuple):
        start: int
        end: int
        kind: str
        text: str

    spans: list[str] = []
    cursor = 0
    length = len(value)
    hits: list[_Hit] = []

    for m in _EMAIL_RE.finditer(value):
        hits.append(_Hit(m.start(), m.end(), "email", m.group(0)))
    for m in _DOMAIN_RE.finditer(value):
        # Skip the domain part already captured by an email match.
        if any(h.start <= m.start() and m.end() <= h.end for h in hits):
            continue
        hits.append(_Hit(m.start(), m.end(), "domain", m.group(0)))
    for m in _IPV4_RE.finditer(value):
        if any(h.start <= m.start() and m.end() <= h.end for h in hits):
            continue
        hits.append(_Hit(m.start(), m.end(), "ipv4", m.group(0)))
    for m in _BRACKETED_IPV6_RE.finditer(value):
        if any(h.start <= m.start() and m.end() <= h.end for h in hits):
            continue
        hits.append(_Hit(m.start() + 1, m.end() - 1, "ip", m.group(1)))

    hits.sort(key=lambda h: (h.start, h.end))
    # Drop overlaps by keeping earliest-starting, longest-first hits.
    deduped: list[_Hit] = []
    last_end = -1
    for h in hits:
        if h.start < last_end:
            continue
        deduped.append(h)
        last_end = h.end

    for h in deduped:
        if cursor < h.start:
            spans.append(format_html("{}", value[cursor : h.start]))
        if h.kind == "email":
            url = _contact_url("tx_mail:contact-messages", org_slug, {"email": h.text})
        elif h.kind == "domain":
            url = _contact_url("tx_mail:contact-messages", org_slug, {"domain": h.text})
        else:
            url = _contact_url("tx_mail:contact-reports", org_slug, {"ip": h.text})
        spans.append(format_html('<a class="link" href="{}">{}</a>', url, h.text))
        cursor = h.end
    if cursor < length:
        spans.append(format_html("{}", value[cursor:]))
    return spans


@register.filter
def header_value(value: str, org) -> str:
    """Render an RFC 5322 header value with every entity turned into a link.

    Emails link to the contact-timeline messages view, domains to the same
    view, and IP addresses to the contact-timeline reports view. Other text
    passes through auto-escaped.
    """
    if not value:
        return ""
    spans = _entity_spans(value, _org_slug(org))
    if not spans:
        return format_html("{}", value)
    return format_html("{}", format_html_join("", "{}", ((s,) for s in spans)))


_email_formatter = HtmlFormatter(cssclass="highlight-email")


@register.filter
def highlight_email(value: str) -> str:
    """Render a raw RFC 822 message with Pygments' :class:`EmailLexer`.

    The output is HTML with ``highlight-email`` wrapper classes that the
    stylesheet in ``src/css/app.css`` styles. Returns the original value
    when empty.
    """
    if not value:
        return ""
    return mark_safe(highlight(value, EmailLexer(), _email_formatter))
