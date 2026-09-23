"""SMTP submission details relay shows to organization members."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _


def get_submission_context(request) -> dict:
    """Return the submission hostname and ports members connect to."""
    implicit_tls_ports = settings.RELAY_SMTP_IMPLICIT_TLS_PORTS
    return {
        "smtp_hostname": f"smtp.{request.get_host().split(':')[0]}",
        "smtp_starttls_ports": tuple(
            port
            for port in settings.RELAY_SMTP_SUBMISSION_PORTS
            if port not in implicit_tls_ports
        ),
        "smtp_implicit_tls_ports": implicit_tls_ports,
    }


def get_submission_uri(request, org_slug, key="") -> str:
    """Return the implicit TLS submission URI, carrying the key when it is known."""
    credentials = f"{org_slug}:{key}" if key else f"{org_slug}:<{_('credential key')}>"
    port = settings.RELAY_SMTP_IMPLICIT_TLS_PORTS[0]
    return (
        f"smtps://{credentials}@{get_submission_context(request)['smtp_hostname']}"
        f":{port}"
    )
