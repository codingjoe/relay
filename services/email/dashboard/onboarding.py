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
        has_outgoing_message = OutgoingMessage.objects.filter(org=org).exists()
        has_credential = bool(credentials)
        connected_credential = get_connected_credential(credentials)
        first_steps = (
            has_outgoing_message,
            has_credential,
            connected_credential is not None,
        )
        context = {
            "has_outgoing_message": has_outgoing_message,
            "has_credential": has_credential,
            "connected_credential": connected_credential,
            "first_steps": first_steps,
            "onboarding_complete": all(first_steps),
            "sending_domains": [
                domain for domain in domains if domain.is_sending_verified
            ],
        }
        request.email_context = context
    return context
