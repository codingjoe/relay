"""SMTP submission details relay shows to organization members."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _


def get_submission_context() -> dict:
    """
    Return the submission hostname and ports members connect to.

    The hostname comes from the configured public host rather than the
    request, so a member reading the page over an internal or preview host
    still gets the address their mail client has to reach.
    """
    implicit_tls_ports = settings.RELAY_SMTP_IMPLICIT_TLS_PORTS
    return {
        "smtp_hostname": settings.RELAY_SMTP_PUBLIC_HOSTNAME,
        "smtp_starttls_ports": tuple(
            port
            for port in settings.RELAY_SMTP_SUBMISSION_PORTS
            if port not in implicit_tls_ports
        ),
        "smtp_implicit_tls_ports": implicit_tls_ports,
    }


def get_submission_uri(org_slug, key="") -> str:
    """Return the implicit TLS submission URI, carrying the key when it is known."""
    credentials = f"{org_slug}:{key}" if key else f"{org_slug}:<{_('credential key')}>"
    context = get_submission_context()
    port = context["smtp_implicit_tls_ports"][0]
    return f"smtps://{credentials}@{context['smtp_hostname']}:{port}"
