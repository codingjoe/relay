import logging
from datetime import timedelta

from django.tasks import task
from django.utils import timezone

from .models import DmarcFailureReport, DmarcReport
from .types import DmarcEvaluation

logger = logging.getLogger(__name__)


@task
def parse_dmarc_report(report_pk):
    """Parse a received DMARC aggregate report and store its records."""
    report = DmarcReport.objects.get(pk=report_pk)
    raw_bytes = report.raw_body.read()
    parsed_report, records = DmarcReport.parse_from_email(raw_bytes)

    report.reporting_org = parsed_report.reporting_org
    report.reporting_email = parsed_report.reporting_email
    report.report_id = parsed_report.report_id
    report.begin_at = parsed_report.begin_at
    report.end_at = parsed_report.end_at
    report.save(
        update_fields=[
            "reporting_org",
            "reporting_email",
            "report_id",
            "begin_at",
            "end_at",
        ]
    )
    for record in records:
        record.report = report
    if records:
        from .models import DmarcRecord

        DmarcRecord.objects.bulk_create(records)


@task
def parse_dmarc_failure_report(report_pk):
    """Parse a received DMARC forensic (RUF) report."""
    report = DmarcFailureReport.objects.get(pk=report_pk)
    raw_bytes = report.raw_body.read()
    parsed = DmarcFailureReport.parse_from_email(raw_bytes)

    report.source_ip_address = parsed.source_ip_address
    report.arrival_at = parsed.arrival_at
    report.original_mail_from = parsed.original_mail_from
    report.original_rcpt_to = parsed.original_rcpt_to
    report.authentication_results = parsed.authentication_results
    report.delivery_result = parsed.delivery_result
    report.original_headers = parsed.original_headers
    report.save(
        update_fields=[
            "source_ip_address",
            "arrival_at",
            "original_mail_from",
            "original_rcpt_to",
            "authentication_results",
            "delivery_result",
            "original_headers",
        ]
    )


@task
def evaluate_incoming_message(message_pk):
    """Evaluate DMARC for an incoming message. If the evaluation fails, generate a RUF report."""
    from domains.models import Domain
    from services.email.mx.models import IncomingMessage

    message = IncomingMessage.objects.get(pk=message_pk)
    evaluation = DmarcEvaluation.from_message(message)

    if evaluation.disposition != "none":
        try:
            domain = Domain.objects.root_for(message.receiving_domain)
        except Domain.DoesNotExist:
            logger.warning(
                "No domain was found for the RUF report: %s", message.receiving_domain
            )
        else:
            if domain.dmarc_ruf_reporting_address:
                DmarcFailureReport.send_ruf_report(message, evaluation)


@task
def generate_daily_rua_reports():
    """Generate and send daily DMARC RUA reports for all verified domains."""
    from domains.models import Domain
    from services.email.mx.models import IncomingMessage

    end_at = timezone.now()
    begin_at = end_at - timedelta(days=1)

    for domain in Domain.objects.filter(verified_at__isnull=False):
        if not domain.dmarc_reporting_address:
            continue
        messages = IncomingMessage.objects.filter(
            receiving_domain__iexact=domain.name,
            created_at__gte=begin_at,
            created_at__lte=end_at,
        )
        evaluations = [DmarcEvaluation.from_message(msg) for msg in messages]
        if evaluations:
            DmarcReport.send_rua_report(domain, evaluations, begin_at, end_at)
