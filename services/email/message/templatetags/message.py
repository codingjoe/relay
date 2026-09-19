"""Email syntax highlighting template filter."""

from datetime import timedelta

from django import template
from django.utils.formats import number_format
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.email import EmailLexer

from ..lexers import AuthenticationResultsLexer, DkimTagLexer, HeaderValueLexer

register = template.Library()

email_formatter = HtmlFormatter(cssclass="highlight-email")


def render(value: str, lexer) -> str:
    """Convert a value to syntax-colored HTML with a Pygments lexer."""
    if not value:
        return ""
    return mark_safe(highlight(value, lexer, email_formatter))


@register.filter
def human_duration(value: timedelta) -> str:
    """Render a duration as `0.3 s` or `40 ms`, so a card reads at a glance."""
    seconds = value.total_seconds()
    if seconds < 0.1:
        return f"{number_format(seconds * 1000, 0)} ms"
    if seconds < 60:
        return f"{number_format(seconds, 1)} s"
    minutes, remainder = divmod(round(seconds), 60)
    if not remainder:
        return f"{number_format(minutes, 0)} min"
    return f"{number_format(minutes, 0)} min {number_format(remainder, 0)} s"


@register.filter
def highlight_email(value: str) -> str:
    """Convert a raw RFC 822 message to syntax-colored HTML."""
    return render(value, EmailLexer())


@register.filter
def highlight_header(value: str, name: str = "") -> str:
    """Convert an email header value to syntax-colored HTML."""
    match name.lower():
        case "dkim-signature" | "arc-message-signature" | "arc-seal":
            return render(value, DkimTagLexer())
        case "authentication-results" | "arc-authentication-results":
            return render(value, AuthenticationResultsLexer())
        case _:
            return render(value, HeaderValueLexer())
