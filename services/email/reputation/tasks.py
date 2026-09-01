import logging

from django.db import transaction
from django.tasks import task
from django.utils import timezone

from accounts.models import Organization
from domains.models import Domain
from services.email.message.models import Message
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage

from . import evaluation
from .models import FblReport

logger = logging.getLogger(__name__)


def resolve_fbl_owner(feedback_id: str) -> tuple[Organization, Domain] | None:
    """Return the org and domain a Feedback-ID attributes a report to.

    Every outgoing message carries the Feedback-ID relay minted when the
    message was submitted, and the provider echoes it in the report.
    Anything else returns `None`.
    """
    try:
        original = (
            OutgoingMessage.objects.select_related(
                "org",
                "domain",
            ).get(feedback_id=feedback_id)
            if feedback_id
            else None
        )
    except OutgoingMessage.DoesNotExist:
        original = None
    return None if original is None else (original.org, original.domain)


@task
def create_held_outgoing_fbl_report(message_pk, org_id):
    """Store a relay-generated FBL report for a held outgoing message.

    The held message counts as spam against the organization's quota even
    though it was never relayed. Queues an org evaluation after the
    report is stored.
    """
    message = OutgoingMessage.objects.get(pk=message_pk)
    report = FblReport.create_for_spam(message)
    check_org_reputation.enqueue(org_id=org_id)
    return report.pk


@task
def create_quarantined_incoming_fbl_report(message_pk):
    """Store a visibility-only relay FBL report for a quarantined message."""
    message = IncomingMessage.objects.get(pk=message_pk)
    return FblReport.create_for_spam(message)


@task
def create_provider_fbl_report(message_pk):
    """Store a provider FBL report for an ingested message and queue parsing."""
    message = IncomingMessage.objects.get(pk=message_pk)
    report = FblReport.create_for_incoming(message)
    parse_fbl_report.enqueue(report_pk=str(report.pk))
    return report


@task
def parse_fbl_report(report_pk):
    """Fill the stored fields from the referenced message's raw ARF body.

    Attribute the report to the sending organization only when the
    provider echoes the message's Feedback-ID, then queue an org
    evaluation.

    Logs and keeps the stored fields when the body is not an ARF email.
    """
    report = FblReport.objects.select_related("message").get(pk=report_pk)
    feedback_id = ""
    try:
        parsed, feedback_id = FblReport.parse_from_email(report.message.raw_body.read())
    except ValueError:
        logger.warning("FBL report %r is not an ARF email", report_pk)
        parsed = None
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

    owner = resolve_fbl_owner(feedback_id)
    update_fields = [
        "org",
        "domain",
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
    with transaction.atomic():
        if owner is not None:
            report.org, report.domain = owner
            # Attached parent messages carry child statuses; save() would
            # reject them, so rebind org and domain with a queryset update.
            Message.objects.filter(pk=report.message_id).update(
                org=owner[0], domain=owner[1], modified_at=timezone.now()
            )
        report.save(update_fields=update_fields)

    check_org_reputation.enqueue(org_id=report.org_id)


@task
def check_org_reputation(org_id):
    """Evaluate rates for an organization and suspend it permanently on a
    threshold breach."""
    evaluation.check_org_reputation(Organization.objects.get(pk=org_id))
