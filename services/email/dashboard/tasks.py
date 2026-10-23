import logging

from django.conf import settings
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django.utils import timezone
from django_letter.exceptions import InvalidUserError

from accounts.models import Membership, Organization

from .emails import EMAIL_BY_STAGE
from .onboarding import SEND_OFFSETS, OnboardingStage, get_onboarding_state, send_time

logger = logging.getLogger(__name__)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def schedule_onboarding_emails(org_pk, from_now=False):
    """Queue every mail of the sequence for the time it is due."""
    try:
        org = Organization.objects.get(pk=org_pk)
    except Organization.DoesNotExist:
        logger.info("Dropped the onboarding sequence for a missing organization")
    else:
        start = timezone.now() if from_now else org.created_at
        for stage, offset in SEND_OFFSETS.items():
            send_onboarding_email.using(run_after=send_time(start, offset)).enqueue(
                org_pk=org.pk, stage=stage
            )


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_onboarding_email(org_pk, stage):
    """Mail one onboarding step to the organization's admins."""
    stage = OnboardingStage(stage)
    try:
        org = Organization.objects.get(pk=org_pk)
    except Organization.DoesNotExist:
        logger.info("Dropped onboarding mail %r for a missing organization", stage)
    else:
        if org.suspended_at:
            logger.info("Stopped onboarding mail %r for suspended %r", stage, org)
        elif (state := get_onboarding_state(org))["onboarding_complete"]:
            logger.info(
                "Stopped onboarding mail %r for %r, onboarding is complete", stage, org
            )
        else:
            email_class = EMAIL_BY_STAGE[stage]
            with mailers.default as mailer:
                for membership in (
                    org.memberships.filter(role=Membership.Role.ADMIN)
                    .for_notification(email_class.notification)
                    .select_related("user")
                ):
                    try:
                        mailer.send_messages(
                            [
                                email_class.to_user(
                                    membership.user,
                                    org=org,
                                    state=state,
                                    base_url=settings.MCP_BASE_URL,
                                    language=settings.LANGUAGE_CODE,
                                )
                            ]
                        )
                    except OSError, InvalidUserError:
                        logger.exception(
                            "Onboarding email for user %r failed", membership.user_id
                        )
