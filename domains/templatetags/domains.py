"""Template filters for the domains app."""

from django.template import Library

from ..models import Domain

register = Library()


@register.filter
def relative_record_name(record_name: str, domain: Domain) -> str:
    """Return the name as a DNS provider expects it, `@` at the apex."""
    match record_name:
        case name if name == domain.name:
            relative_name = "@"
        case name if name.endswith(f".{domain.name}"):
            relative_name = name.removesuffix(f".{domain.name}")
        case name:
            relative_name = name
    return relative_name


@register.filter
def apex_suffix(record_name: str, domain: Domain) -> str:
    """Return the zone a relative record name sits in, empty at the apex."""
    if not record_name.endswith(f".{domain.name}"):
        return ""
    return f".{domain.name}"
