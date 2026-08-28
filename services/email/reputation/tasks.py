import logging

from django.tasks import task

from accounts.models import Organization

from . import evaluation
from .models import FblReport

logger = logging.getLogger(__name__)


@task
def parse_fbl_report(report_pk):
    """Fill stored report fields from the raw ARF body, then queue an org
    evaluation.

    Logs and keeps the stored fields when the body is not an ARF email.
    """
    report = FblReport.objects.get(pk=report_pk)
    raw_bytes = report.raw_body.read()
    try:
        parsed = FblReport.parse_from_email(raw_bytes)
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


@task
def check_org_reputation(org_id):
    """Evaluate rates for an organization and lock it permanently on a
    threshold breach."""
    evaluation.check_org_reputation(Organization.objects.get(pk=org_id))
