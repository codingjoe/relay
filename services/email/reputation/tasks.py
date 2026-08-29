import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.tasks import task
from django.utils import timezone

from accounts.models import Organization
from domains.models import Domain
from services.email.message.models import Message
from services.email.msa.models import OutgoingMessage

from . import evaluation
from .models import FblReport

logger = logging.getLogger(__name__)


def resolve_fbl_owner(
    original_mail_from: str, feedback_id: str = ""
) -> tuple[Organization, Domain] | None:
    """Return the org and domain that sent the message a report is about.

    The per-message proof the provider echoes is either the full VERP
    envelope sender (`bounce+<message-id>@<sender-domain>`) or the
    Feedback-ID that relay minted when the message was submitted.
    Anything else returns `None`.
    """
    token = original_mail_from.partition("@")[0].partition("+")[2]
    try:
        original = OutgoingMessage.objects.select_related(
            "org",
            "domain",
        ).get(pk=token)
    except ValidationError, OutgoingMessage.DoesNotExist:
        original = None
    else:
        if original.domain is None or original_mail_from != (
            f"{settings.RELAY_BOUNCE_LOCAL_PART}+{original.pk}"
            f"@{original.domain.sender_domain}"
        ):
            original = None
    if original is None:
        try:
            original = (
                OutgoingMessage.objects.select_related(
                    "org",
                    "domain",
                )
                .exclude(feedback_id="")
                .get(feedback_id=feedback_id)
            )
        except OutgoingMessage.DoesNotExist:
            return None
    if original.domain is None:
        return None
    return original.org, original.domain


@task
def parse_fbl_report(report_pk):
    """Fill the stored fields from the referenced message's raw ARF body.

    Attribute the report to the sending organization only when the
    provider echoes the exact original VERP envelope sender or the
    message's Feedback-ID, then queue an org evaluation.

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

    owner = resolve_fbl_owner(
        original_mail_from=report.original_mail_from,
        feedback_id=feedback_id,
    )
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
