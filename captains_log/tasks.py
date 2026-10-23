import logging
from datetime import timedelta

from crontask import cron
from django.conf import settings
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django.utils import timezone

from accounts.models import Membership

from .content import CaptainsLogContent
from .emails import StationLogEmail, station_log_notification

logger = logging.getLogger(__name__)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_station_log(slug):
    """Mail one published station log to the members who want it."""
    metadata = CaptainsLogContent.get_article_metadata(slug)
    mailer = mailers.default
    with mailer:
        for member in {
            membership.user
            for membership in (
                Membership.objects.filter(org__suspended_at__isnull=True)
                .for_notification(station_log_notification)
                .select_related("user")
            )
        }:
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
            except (OSError, ValueError) as exc:
                member_pk = member.pk
                logger.warning(
                    "Station log for user %r failed: %s",
                    member_pk,
                    type(exc).__name__,
                )


@cron("0 15 * * *")
@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_station_log_announcements():
    """Queue the announcement for each log published yesterday."""
    yesterday = timezone.localdate() - timedelta(days=1)
    for slug, metadata in CaptainsLogContent.get_articles():
        if metadata["date"] == yesterday:
            send_station_log.enqueue(slug=slug)
