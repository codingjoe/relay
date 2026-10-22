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


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_station_log(slug, *, dry_run=False):
    """Mail one published station log to the members who want it."""
    members: dict[int, User] = {}
    for membership in (
        Membership.objects.filter(org__suspended_at__isnull=True)
        .for_notification(station_log_notification)
        .select_related("user", "org")
    ):
        if not SuppressionEntry.objects.is_suppressed(
            membership.org,
            membership.user.email,
        ):
            members[membership.user_id] = membership.user
    if dry_run:
        return len(members)
    metadata = CaptainsLogContent.get_article_metadata(slug)
    mailer = mailers.default
    with mailer:
        for member in members.values():
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
    return len(members)
