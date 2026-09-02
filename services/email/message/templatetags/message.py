"""Email syntax highlighting template filter."""

from django import template
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.email import EmailLexer

from ..lexers import AuthenticationResultsLexer, DkimTagLexer

register = template.Library()

email_formatter = HtmlFormatter(cssclass="highlight-email")


def render(value: str, lexer) -> str:
    """Convert a value to syntax-colored HTML with a Pygments lexer."""
    if not value:
        return ""
    return mark_safe(highlight(value, lexer, email_formatter))


@register.filter
def highlight_email(value: str) -> str:
    """Convert a raw RFC 822 message to syntax-colored HTML."""
    return render(value, EmailLexer())


@register.filter
def highlight_dkim(value: str) -> str:
    """Convert a DKIM-Signature header value to syntax-colored HTML."""
    return render(value, DkimTagLexer())


@register.filter
def highlight_authres(value: str) -> str:
    """Convert an Authentication-Results header to syntax-colored HTML."""
    return render(value, AuthenticationResultsLexer())
