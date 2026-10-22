import datetime
import logging

from crontask import cron
from django.conf import settings
from django.core.mail import mailers
from django.db.models.functions import Now
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django.utils import timezone
from django_letter.exceptions import InvalidUserError
from django_letter.notifications.models import NotificationPreference

from accounts.models import Membership

from .emails import EMAIL_BY_STAGE
from .models import OnboardingCampaign
from .onboarding import get_onboarding_state

logger = logging.getLogger(__name__)

CLAIM_WINDOW = datetime.timedelta(hours=1)  # one cron interval


@cron("0 * * * *")
@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_due_onboarding_emails():
    """Queue the next email of every sequence that is due."""
    due_campaigns = OnboardingCampaign.objects.filter(
        next_send_at__lte=timezone.now(),
        completed_at__isnull=True,
        org__suspended_at__isnull=True,
    )
    for campaign_pk in due_campaigns.values_list("pk", flat=True).iterator():
        send_onboarding_email.enqueue(campaign_pk=campaign_pk)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_onboarding_email(campaign_pk):
    """Mail the campaign's next email to the organization's admins, or close it."""
    try:
        campaign = OnboardingCampaign.objects.select_related("org").get(pk=campaign_pk)
    except OnboardingCampaign.DoesNotExist:
        logger.info("Dropped onboarding campaign %r that no longer exists", campaign_pk)
    else:
        if claimed := OnboardingCampaign.objects.filter(
            pk=campaign.pk,
            next_send_at__lte=Now(),
            completed_at__isnull=True,
            org__suspended_at__isnull=True,
        ).update(next_send_at=Now() + CLAIM_WINDOW, modified_at=Now()):
            logger.debug("Claimed %s onboarding campaign row(s)", claimed)
            state = get_onboarding_state(campaign.org)
            if state["onboarding_complete"]:
                campaign.complete()
            else:
                mailer = mailers.default
                base_url = (
                    f"{'http' if settings.DEBUG else 'https'}://"
                    f"{settings.RELAY_PLATFORM_DOMAIN}"
                )
                email_class = EMAIL_BY_STAGE[campaign.stage]
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
                campaign.mark_email_sent()
        else:
            logger.info("Skipped onboarding campaign %r that is not due", campaign)
