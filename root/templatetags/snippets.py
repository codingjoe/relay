"""Template tags for embedding the landing-page code samples."""

from pathlib import Path

from django import template
from django.utils.html import conditional_escape

register = template.Library()

SNIPPET_DIR = Path(__file__).resolve().parent.parent / "snippets"


@register.simple_tag
def snippet(name):
    """Return the escaped source of one code sample from `root/snippets/`."""
    path = (SNIPPET_DIR / name).resolve()
    if not path.is_relative_to(SNIPPET_DIR):
        raise ValueError(f"{name} is not a code sample")  # noqa: TRY003
    return conditional_escape(path.read_text())
