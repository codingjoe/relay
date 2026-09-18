from domains.models import Domain
from services.email.msa.models import OutgoingMessage


def get_onboarding_state(org) -> dict:
    """Return each first-steps item and whether the organization finished it."""
    domains = list(Domain.objects.filter(org=org))
    return {
        "managed_domain": next(
            (domain for domain in domains if domain.is_managed and domain.verified_at),
            None,
        ),
        "has_custom_domain": any(not domain.is_managed for domain in domains),
        "has_outgoing_message": OutgoingMessage.objects.filter(org=org).exists(),
    }


def is_onboarding_complete(org) -> bool:
    """Return whether every first-steps item is done."""
    state = get_onboarding_state(org)
    return bool(
        state["managed_domain"]
        and state["has_custom_domain"]
        and state["has_outgoing_message"]
    )


def get_sending_domains(org) -> list[Domain]:
    """Return the domains an organization can send from."""
    return [
        domain
        for domain in Domain.objects.filter(org=org)
        if domain.is_sending_verified
    ]
