import logging

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


def resolve_fbl_owner(rcpt_to, original_mail_from):
    """Return the org and domain that sent the message a report is about.

    FBL reports usually arrive on a single reporting address, regardless
    of the recipient. Preference is a VERP token in the report recipient
    (fbl+<message-id>@<domain>) that references the original outgoing
    message. Without a token, the original envelope sender domain from
    the report payload resolves the customer domain; managed domains are
    excluded.

    Returns `None` when the report cannot be attributed to an org.
    """
    local_part = rcpt_to.split("@", 1)[0]
    token = local_part.split("+", 1)[1] if "+" in local_part else ""
    if token:
        try:
            original = OutgoingMessage.objects.select_related(
                "org",
                "domain",
            ).get(pk=token)
        except ValueError, ValidationError, OutgoingMessage.DoesNotExist:
            original = None
        else:
            return original.org, original.domain
    mail_from_domain = original_mail_from.split("@")[-1]
    if not mail_from_domain:
        return None
    try:
        domain = Domain.objects.root_for(mail_from_domain, include_managed=False)
    except Domain.DoesNotExist:
        return None
    return domain.org, domain


@task
def parse_fbl_report(report_pk):
    """Fill the stored fields from the referenced message's raw ARF body,
    route the report to the sending organization, then queue an org
    evaluation.

    Logs and keeps the stored fields when the body is not an ARF email.
    """
    report = FblReport.objects.select_related("message").get(pk=report_pk)
    try:
        parsed = FblReport.parse_from_email(report.message.raw_body.read())
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
        rcpt_to=report.message.rcpt_to,
        original_mail_from=report.original_mail_from,
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
