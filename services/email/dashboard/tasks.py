import datetime
import logging

from crontask import cron
from django.conf import settings
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django.utils import timezone
from django_letter.exceptions import InvalidUserError
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership, Organization

from .emails import EMAIL_BY_STAGE
from .models import OnboardingMail, send_time
from .onboarding import get_onboarding_state

logger = logging.getLogger(__name__)

# Give the cron a day of slack past the last offset before an organization
# stops being considered at all.
SEQUENCE_WINDOW = datetime.timedelta(
    days=OnboardingMail.SEND_OFFSETS[OnboardingMail.Stage.LAST_REMINDER] + 1
)


def due_stage(org, now):
    """Return the earliest mail that is due and not sent yet."""
    sent = {mail.stage for mail in org.onboarding_mails.all()}
    return next(
        (
            stage
            for stage, days in OnboardingMail.SEND_OFFSETS.items()
            if stage not in sent and send_time(org.created_at, days) <= now
        ),
        None,
    )


@cron("0 * * * *")
@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_due_onboarding_emails():
    """Queue the next unsent onboarding mail of every organization that is due."""
    now = timezone.now()
    orgs = (
        Organization.objects.filter(
            created_at__gte=now - SEQUENCE_WINDOW,
            suspended_at__isnull=True,
        )
        .only("pk", "created_at")
        .prefetch_related("onboarding_mails")
    )
    for org in orgs:
        if stage := due_stage(org, now):
            send_onboarding_email.enqueue(org_pk=org.pk, stage=stage)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_onboarding_email(org_pk, stage):
    """Mail one onboarding step to the organization's admins."""
    stage = OnboardingMail.Stage(stage)
    try:
        org = Organization.objects.get(pk=org_pk)
    except Organization.DoesNotExist:
        logger.info("Dropped onboarding mail %r for a missing organization", stage)
    else:
        state = get_onboarding_state(org)
        if state["onboarding_complete"]:
            logger.info(
                "Stopped onboarding mail %r for %r, onboarding is complete", stage, org
            )
        else:
            email_class = EMAIL_BY_STAGE[stage]
            _, created = OnboardingMail.objects.get_or_create(org=org, stage=stage)
            if created:
                mailer = mailers.default
                base_url = (
                    f"{'http' if settings.DEBUG else 'https'}://"
                    f"{settings.RELAY_PLATFORM_DOMAIN}"
                )
                with mailer:
                    for membership in (
                        org.memberships.filter(
                            role=Membership.Role.ADMIN,
                            user__is_active=True,
                        )
                        .select_related("user")
                        .iterator()
                    ):
                        if NotificationPreference.objects.is_enabled(
                            email_class.notification, membership.user.email
                        ):
                            try:
                                mailer.send_messages(
                                    [
                                        email_class.to_user(
                                            membership.user,
                                            org=org,
                                            state=state,
                                            base_url=base_url,
                                            language=settings.LANGUAGE_CODE,
                                        )
                                    ]
                                )
                            except OSError, InvalidUserError:
                                logger.exception(
                                    "Onboarding email for user %r failed",
                                    membership.user,
                                )
            else:
                logger.info(
                    "Skipped onboarding mail %r for %r that another worker sent",
                    stage,
                    org,
                )
