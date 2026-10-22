import logging
from datetime import timedelta

from crontask import cron
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django.utils import timezone

from accounts.models import Membership
from services.email.msa.models import SuppressionEntry

from .content import CaptainsLogContent, publication_date
from .emails import StationLogEmail, station_log_notification

logger = logging.getLogger(__name__)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_station_log(slug):
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


@cron("0 9 * * *")
@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_station_log_announcements():
    """Queue the announcement for each log published yesterday."""
    yesterday = timezone.localdate() - timedelta(days=1)
    for slug, metadata in CaptainsLogContent.get_articles():
        if publication_date(metadata) == yesterday:
            send_station_log.enqueue(slug=slug)
