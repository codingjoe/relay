import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task

from accounts.models import Membership
from captains_log.content import CaptainsLogContent
from services.email.msa.models import SuppressionEntry

from .emails import StationLogEmail, station_log_notification

logger = logging.getLogger(__name__)


def station_log_recipients() -> dict[int, User]:
    """Return one user per member who wants the station log."""
    memberships = (
        Membership.objects.filter(org__suspended_at__isnull=True)
        .for_notification(station_log_notification)
        .select_related("user", "org")
    )
    return {
        membership.user_id: membership.user
        for membership in memberships
        if not SuppressionEntry.objects.is_suppressed(
            membership.org,
            membership.user.email,
        )
    }


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_station_log(slug):
    """Mail one published station log to the members who want it."""
    metadata = CaptainsLogContent.get_article_metadata(slug)
    mailer = mailers.default
    with mailer:
        for member in station_log_recipients().values():
            try:
                mailer.send_messages(
                    [
                        StationLogEmail.to_user(
                            member,
                            slug=slug,
                            metadata=metadata,
                            language=settings.LANGUAGE_CODE,
                        )
                    ]
                )
            except OSError:
                logger.exception("Station log for user %r failed", member.pk)
