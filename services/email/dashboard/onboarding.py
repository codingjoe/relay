import datetime

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from domains.models import Domain
from services.email.msa.models import MsaCredential, OutgoingMessage

# Reminders land at 09:00 project time; weekend landings move to Monday.
SEND_HOUR = 9


def send_time(
    start: datetime.datetime, offset: datetime.timedelta
) -> datetime.datetime:
    """Return the 09:00 weekday that is `offset` after `start`."""
    if not offset:
        return start
    moment = (timezone.localtime(start) + offset).replace(
        hour=SEND_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    while moment.weekday() >= 5:
        moment += datetime.timedelta(days=1)
    return moment


class OnboardingStage(models.TextChoices):
    WELCOME = "welcome", _("welcome")
    FIRST_REMINDER = "first-reminder", _("first reminder")
    SECOND_REMINDER = "second-reminder", _("second reminder")
    LAST_REMINDER = "last-reminder", _("last reminder")


# Delay after sign-up; each mail is due on its own day.
SEND_OFFSETS = {
    OnboardingStage.WELCOME: datetime.timedelta(0),
    OnboardingStage.FIRST_REMINDER: datetime.timedelta(days=2),
    OnboardingStage.SECOND_REMINDER: datetime.timedelta(days=6),
    OnboardingStage.LAST_REMINDER: datetime.timedelta(days=13),
}


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
