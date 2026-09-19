from domains.models import Domain
from services.email.msa.models import OutgoingMessage


def get_email_context(org, request) -> dict:
    """
    Return the first-steps state and the sending domains of one organization.

    The shared layout, the first-steps view, and the test email dialog all
    ask for this on the same page, so the result is memoized on the request:
    one domain query and one existence check per page.
    """
    try:
        context = request.email_context
    except AttributeError:
        domains = list(Domain.objects.filter(org=org))
        managed_domain = next(
            (domain for domain in domains if domain.is_managed and domain.verified_at),
            None,
        )
        has_custom_domain = any(not domain.is_managed for domain in domains)
        has_outgoing_message = OutgoingMessage.objects.filter(org=org).exists()
        context = {
            "managed_domain": managed_domain,
            "has_custom_domain": has_custom_domain,
            "has_outgoing_message": has_outgoing_message,
            "onboarding_complete": bool(
                managed_domain and has_custom_domain and has_outgoing_message
            ),
            "sending_domains": [
                domain for domain in domains if domain.is_sending_verified
            ],
        }
        request.email_context = context
    return context
