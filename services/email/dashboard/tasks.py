import datetime
import logging

from crontask import cron
from django.conf import settings
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django.utils import timezone
from django_letter.exceptions import InvalidUserError
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership

from .emails import EMAIL_BY_STAGE
from .models import OnboardingCampaign
from .onboarding import get_onboarding_state

logger = logging.getLogger(__name__)

# The sequence runs for a week and the cron may run a little late, so give it
# a day of slack before an old campaign stops being considered at all.
SEQUENCE_WINDOW = datetime.timedelta(days=OnboardingCampaign.SEND_OFFSETS[-1] + 1)


@cron("0 * * * *")
@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_due_onboarding_emails():
    """Queue the next email of every sequence that is due."""
    now = timezone.now()
    due_campaigns = (
        OnboardingCampaign.objects.filter(
            sent_count__lt=len(OnboardingCampaign.SEQUENCE),
            created_at__gte=now - SEQUENCE_WINDOW,
            org__suspended_at__isnull=True,
        )
        .only("pk", "created_at", "sent_count")
        .iterator()
    )
    for campaign in due_campaigns:
        if campaign.next_send_at <= now:
            send_onboarding_email.enqueue(campaign_pk=campaign.pk)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_onboarding_email(campaign_pk):
    """Mail the campaign's next email to the organization's admins."""
    try:
        campaign = OnboardingCampaign.objects.select_related("org").get(pk=campaign_pk)
    except OnboardingCampaign.DoesNotExist:
        logger.info("Dropped onboarding campaign %r that no longer exists", campaign_pk)
    else:
        email_class = EMAIL_BY_STAGE.get(campaign.stage)
        state = get_onboarding_state(campaign.org) if email_class else None
        if email_class is None:
            logger.debug(
                "Skipped onboarding campaign %r, the sequence ran out", campaign
            )
        elif state["onboarding_complete"]:
            logger.info(
                "Stopped onboarding campaign %r, onboarding is complete", campaign
            )
        elif not campaign.claim():
            logger.info(
                "Skipped onboarding campaign %r that another worker claimed", campaign
            )
        else:
            campaign.sent_count += 1
            mailer = mailers.default
            base_url = (
                f"{'http' if settings.DEBUG else 'https'}://"
                f"{settings.RELAY_PLATFORM_DOMAIN}"
            )
            with mailer:
                for membership in (
                    campaign.org.memberships.filter(
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
                                        campaign=campaign,
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
