from domains.models import Domain
from services.email.msa.models import MsaCredential, OutgoingMessage


def get_connected_credential(credentials):
    """Return the credential an application authenticated with most recently."""
    return max(
        (credential for credential in credentials if credential.last_used_at),
        key=lambda credential: credential.last_used_at,
        default=None,
    )


def get_email_context(org, request) -> dict:
    """Return the first-steps state and the sending domains of one organization."""
    try:
        context = request.email_context
    except AttributeError:
        domains = list(Domain.objects.filter(org=org))
        credentials = list(MsaCredential.objects.filter(org=org))
        managed_domain = next(
            (domain for domain in domains if domain.is_managed and domain.verified_at),
            None,
        )
        has_custom_domain = any(not domain.is_managed for domain in domains)
        has_outgoing_message = OutgoingMessage.objects.filter(org=org).exists()
        connected_credential = get_connected_credential(credentials)
        first_steps = (
            has_outgoing_message,
            connected_credential is not None,
            has_custom_domain,
        )
        context = {
            "managed_domain": managed_domain,
            "has_custom_domain": has_custom_domain,
            "has_outgoing_message": has_outgoing_message,
            "connected_credential": connected_credential,
            "first_steps": first_steps,
            "onboarding_complete": all(first_steps),
            "sending_domains": [
                domain for domain in domains if domain.is_sending_verified
            ],
        }
        request.email_context = context
    return context
