import logging

from crontask import cron
from django.conf import settings
from django.core.mail import mailers
from django.tasks import DEFAULT_TASK_QUEUE_NAME, task
from django_letter.notifications import hash_email
from django_letter.notifications.models import NotificationPreference

from accounts.models import Organization
from services.email.msa.models import OutgoingMessage
from services.email.msa.tasks import resolve_bounce_owner
from services.email.mta.models import IncomingMessage

from . import evaluation
from .digest import build_org_digest, iter_digest_members
from .emails import WeeklyDigestEmail, weekly_digest_notification
from .models import FblReport

logger = logging.getLogger(__name__)


@task()
def create_held_outgoing_fbl_report(message_pk, org_id):
    """
    Store a relay-generated FBL report for a held outgoing message.

    The held message counts as spam against the organization's quota even
    though it was never relayed. Queues an org evaluation after the
    report is stored.
    """
    message = OutgoingMessage.objects.get(pk=message_pk)
    FblReport.create_for_spam(message)
    check_org_reputation.enqueue(org_id=org_id)


@task()
def create_quarantined_incoming_fbl_report(message_pk):
    """Store a visibility-only relay FBL report for a quarantined message."""
    message = IncomingMessage.objects.get(pk=message_pk)
    FblReport.create_for_spam(message)


@task()
def create_provider_fbl_report(message_pk):
    """Store a provider FBL report for an ingested message and queue parsing."""
    message = IncomingMessage.objects.get(pk=message_pk)
    try:
        parsed = FblReport.parse_from_email(message.raw_body.read())
    except ValueError:
        logger.warning("FBL report %r is not an ARF email", message_pk)
        return
    complained_message = resolve_bounce_owner(parsed.original_mail_from)
    if complained_message is None:
        logger.warning(
            "FBL report %r names no message relay sent, kept as a message only",
            message_pk,
        )
        return
    report = FblReport.create_for_incoming(message, complained_message)
    parse_fbl_report.enqueue(report_pk=str(report.pk))


@task()
def parse_fbl_report(report_pk):
    """Fill the stored fields from the referenced message's raw ARF body."""
    report = FblReport.objects.select_related("message").get(pk=report_pk)
    try:
        parsed = FblReport.parse_from_email(report.message.raw_body.read())
    except ValueError:
        logger.warning("FBL report %r is not an ARF email", report_pk)
    else:
        report.feedback_type = parsed.feedback_type
        report.user_agent = parsed.user_agent
        report.version = parsed.version
        report.reporting_org = parsed.reporting_org
        report.reporting_email = parsed.reporting_email
        report.source_ip_address = parsed.source_ip_address
        report.arrival_at = parsed.arrival_at
        report.original_mail_from = parsed.original_mail_from
        report.original_rcpt_to = parsed.original_rcpt_to
        report.original_message_id = parsed.original_message_id
        report.authentication_results = parsed.authentication_results
        report.original_headers = parsed.original_headers
        report.save(
            update_fields=[
                "feedback_type",
                "user_agent",
                "version",
                "reporting_org",
                "reporting_email",
                "source_ip_address",
                "arrival_at",
                "original_mail_from",
                "original_rcpt_to",
                "original_message_id",
                "authentication_results",
                "original_headers",
                "modified_at",
            ]
        )

    check_org_reputation.enqueue(org_id=report.org_id)


@task()
def check_org_reputation(org_id):
    """Evaluate rates for an organization and suspend it on a threshold breach."""
    evaluation.check_org_reputation(Organization.objects.get(pk=org_id))


@cron("0 8 * * Mon")
@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_weekly_digests():
    """Queue one task per organization that is not suspended."""
    for org_id in (
        Organization.objects.filter(suspended_at__isnull=True)
        .values_list("pk", flat=True)
        .iterator()
    ):
        send_org_weekly_digest.enqueue(org_id=org_id)


@task(queue_name=DEFAULT_TASK_QUEUE_NAME)
def send_org_weekly_digest(org_id):
    """Mail the window's numbers to the members the digest reaches."""
    org = Organization.objects.get(pk=org_id)
    if org.suspended_at:
        logger.info("Dropped the weekly digest for suspended organization %r", org_id)
    else:
        digest = build_org_digest(org)
        disabled_hashes = set(
            NotificationPreference.objects.email_hashes(weekly_digest_notification)
        )
        mailer = mailers.default
        with mailer:
            for membership in iter_digest_members(org):
                if hash_email(membership.user.email) not in disabled_hashes:
                    try:
                        mailer.send_messages(
                            [
                                WeeklyDigestEmail.to_user(
                                    membership.user,
                                    digest=digest,
                                    language=settings.LANGUAGE_CODE,
                                )
                            ]
                        )
                    except OSError:
                        logger.exception(
                            "Weekly digest for user %r failed", membership.user_id
                        )
