"""Email syntax highlighting template filter."""

from django import template
from django.utils.safestring import mark_safe
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers.email import EmailLexer

register = template.Library()

email_formatter = HtmlFormatter(cssclass="highlight-email")


@register.filter
def highlight_email(value: str) -> str:
    """Render a raw RFC 822 message with Pygments' `EmailLexer`."""
    if not value:
        return ""
    return mark_safe(highlight(value, EmailLexer(), email_formatter))
