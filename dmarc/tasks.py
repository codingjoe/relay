import logging

from django.tasks import task

from .models import DmarcFailureReport, DmarcReport

logger = logging.getLogger(__name__)


@task
def parse_dmarc_report(report_pk):
    """Parse a received DMARC aggregate report and store its records."""
    report = DmarcReport.objects.get(pk=report_pk)
    raw_bytes = report.raw_body.read()
    parsed_report, records = DmarcReport.parse_from_email(raw_bytes)

    if (
        parsed_report.report_id
        and DmarcReport.objects.filter(
            domain=report.domain, report_id=parsed_report.report_id
        )
        .exclude(pk=report.pk)
        .exists()
    ):
        logger.info(f"Duplicate DMARC report {report_pk}, discarding.")
        report.delete()
        return

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
