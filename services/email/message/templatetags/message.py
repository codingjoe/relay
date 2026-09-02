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
    if not value:
        return ""
    return mark_safe(highlight(value, lexer, email_formatter))


@register.filter
def highlight_email(value: str) -> str:
    """Render a raw RFC 822 message with Pygments' `EmailLexer`."""
    return render(value, EmailLexer())


@register.filter
def highlight_dkim(value: str) -> str:
    """Render a DKIM-Signature tag list with relay's DKIM lexer."""
    return render(value, DkimTagLexer())


@register.filter
def highlight_authres(value: str) -> str:
    """Render an Authentication-Results header with relay's authres lexer."""
    return render(value, AuthenticationResultsLexer())
