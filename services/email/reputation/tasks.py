import logging

from django.tasks import task

from .models import FblReport

logger = logging.getLogger(__name__)


@task
def parse_fbl_report(report_pk):
    """Parse a received FBL complaint report and update its fields."""
    report = FblReport.objects.get(pk=report_pk)
    raw_bytes = report.raw_body.read()
    parsed = FblReport.parse_from_email(raw_bytes)

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
        ]
    )

    if report.domain_id:
        check_domain_reputation.enqueue(domain_id=report.domain_id)


@task
def check_domain_reputation(domain_id):
    """Evaluate bounce and complaint rates for a domain and set or clear the hold."""
    from domains.models import Domain

    domain = Domain.objects.get(pk=domain_id)
    domain.check_reputation()


@task
def check_all_reputations():
    """Check reputation for all verified, non-system domains."""
    from domains.models import Domain

    for domain in Domain.objects.filter(
        verified_at__isnull=False,
        org__isnull=False,
    ):
        domain.check_reputation()
