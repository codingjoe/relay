"""SMTP submission details relay shows to organization members."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _


def get_submission_context() -> dict:
    """Return the submission hostname and ports members connect to."""
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


def get_submission_credentials(org_slug, key="") -> str:
    """Return the user and password of a submission URI."""
    return f"{org_slug}:{key}" if key else f"{org_slug}:<{_('credential key')}>"


def get_submission_uri(org_slug, key="") -> str:
    """Return the submission URI of the smtps scheme, which implies port 465."""
    context = get_submission_context()
    credentials = get_submission_credentials(org_slug, key)
    return f"smtps://{credentials}@{context['smtp_hostname']}"


def get_django_submission_uri(org_slug, key="") -> str:
    """Return the submission URI that django-environ reads as implicit TLS."""
    context = get_submission_context()
    credentials = get_submission_credentials(org_slug, key)
    port = context["smtp_implicit_tls_ports"][0]
    # django-environ maps smtps:// to STARTTLS and never defaults a port.
    return f"smtp+ssl://{credentials}@{context['smtp_hostname']}:{port}"


def get_credential_key_context(request, org_slug) -> dict:
    """Return the one-time credential key of the session, consuming it."""
    raw_key = request.session.pop("raw_key", None)
    context = {}
    if raw_key:
        context = {
            "raw_key": raw_key,
            "smtp_uri_with_key": get_submission_uri(org_slug, key=raw_key),
            "smtp_django_uri_with_key": get_django_submission_uri(
                org_slug, key=raw_key
            ),
        }
    return context
