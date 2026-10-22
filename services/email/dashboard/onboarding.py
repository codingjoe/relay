from django.db import models
from django.utils.translation import gettext_lazy as _

from domains.models import Domain
from services.email.msa.models import MsaCredential, OutgoingMessage


class OnboardingStep(models.TextChoices):
    TEST_MESSAGE = "test-message", _("send test message")
    CREDENTIAL = "credential", _("create sandbox key")
    CONNECT = "connect", _("connect your app")


def get_onboarding_state(org) -> dict:
    """Return the first-steps state and the sending domains of one organization."""
    domains = list(Domain.objects.filter(org=org))
    credentials = list(MsaCredential.objects.filter(org=org))
    has_outgoing_message = OutgoingMessage.objects.filter(org=org).exists()
    has_credential = bool(credentials)
    connected_credential = max(
        (credential for credential in credentials if credential.last_used_at),
        key=lambda credential: credential.last_used_at,
        default=None,
    )
    steps = (
        (OnboardingStep.TEST_MESSAGE, has_outgoing_message),
        (OnboardingStep.CREDENTIAL, has_credential),
        (OnboardingStep.CONNECT, connected_credential is not None),
    )
    completed_steps = sum(done for _, done in steps)
    return {
        "has_outgoing_message": has_outgoing_message,
        "has_credential": has_credential,
        "connected_credential": connected_credential,
        "onboarding_complete": completed_steps == len(steps),
        "next_step": next((step for step, done in steps if not done), None),
        "remaining_steps": len(steps) - completed_steps,
        "onboarding_steps": [
            {"label": step.label, "done": done} for step, done in steps
        ],
        "sending_domains": [domain for domain in domains if domain.is_sending_verified],
    }


def get_email_context(org, request) -> dict:
    """Return the onboarding state, reusing the request's cached copy."""
    try:
        context = request.email_context
    except AttributeError:
        context = get_onboarding_state(org)
        request.email_context = context
    return context
