import logging

from django.conf import settings
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django_letter.exceptions import InvalidUserError

from accounts.models import Membership, Organization

from .emails import EMAIL_BY_STAGE
from .models import OnboardingMail, send_time
from .onboarding import get_onboarding_state

logger = logging.getLogger(__name__)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def schedule_onboarding_emails(org_pk):
    """Queue every mail of the sequence for the time it is due."""
    try:
        org = Organization.objects.get(pk=org_pk)
    except Organization.DoesNotExist:
        logger.info("Dropped the onboarding sequence for a missing organization")
    else:
        for stage, offset in OnboardingMail.SEND_OFFSETS.items():
            send_onboarding_email.using(
                run_after=send_time(org.created_at, offset)
            ).enqueue(org_pk=org.pk, stage=stage)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_onboarding_email(org_pk, stage):
    """Mail one onboarding step to the organization's admins."""
    stage = OnboardingMail.Stage(stage)
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
            claim, created = OnboardingMail.objects.get_or_create(org=org, stage=stage)
            if not created:
                logger.info(
                    "Skipped onboarding mail %r for %r that another worker sent",
                    stage,
                    org,
                )
            else:
                delivered = 0
                failure = None
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
                        except (OSError, InvalidUserError) as exc:
                            failure = exc
                            logger.exception(
                                "Onboarding email for user %r failed", membership.user
                            )
                        else:
                            delivered += 1
                if failure and not delivered:
                    claim.delete()
                    raise failure
