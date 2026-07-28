"""Tasks for parsing DMARC reports and evaluating incoming messages."""

import logging

from django.tasks import task
from django.utils import timezone

from .evaluation import evaluate_dmarc
from .models import DmarcEvaluation, DmarcFailureReport, DmarcRecord, DmarcReport
from .parser import extract_attachment, parse_arf, parse_dmarc_xml
from .report_generator import generate_and_send_rua, generate_and_send_ruf

logger = logging.getLogger(__name__)


@task
def parse_dmarc_report(report_pk):
    """Parse a received DMARC aggregate report and store its records."""
    report = DmarcReport.objects.select_related("incoming_message").get(pk=report_pk)
    try:
        raw_bytes = report.incoming_message.raw_body.read()
        data = extract_attachment(raw_bytes)
        if data is None:
            raise ValueError("No attachment found in DMARC report email.")
        parsed = parse_dmarc_xml(data)
        meta = parsed["metadata"]

        # Check for a duplicate (already-parsed report with same domain + report_id).
        if (
            meta["report_id"]
            and DmarcReport.objects.filter(
                domain=report.domain, report_id=meta["report_id"]
            )
            .exclude(pk=report.pk)
            .exists()
        ):
            logger.info(f"Duplicate DMARC report {report_pk}, discarding.")
            report.delete()
            return

        report.reporting_org = meta["reporting_org"]
        report.reporting_email = meta["reporting_email"]
        report.report_id = meta["report_id"]
        report.begin_at = meta["begin_at"]
        report.end_at = meta["end_at"]

        records = [
            DmarcRecord(report=report, **record_data)
            for record_data in parsed["records"]
        ]
        DmarcRecord.objects.bulk_create(records)
        report.status = DmarcReport.Status.PARSED
        report.error = ""
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to parse DMARC report {report_pk}: {e}")
        report.status = DmarcReport.Status.FAILED
        report.error = str(e)
    finally:
        if report.pk:
            report.save(
                update_fields=[
                    "reporting_org",
                    "reporting_email",
                    "report_id",
                    "begin_at",
                    "end_at",
                    "status",
                    "error",
                ]
            )


@task
def parse_dmarc_failure_report(report_pk):
    """Parse a received DMARC forensic (RUF) report."""
    report = DmarcFailureReport.objects.select_related("incoming_message").get(
        pk=report_pk
    )
    try:
        raw_bytes = report.incoming_message.raw_body.read()
        parsed = parse_arf(raw_bytes)

        report.source_ip_address = parsed["source_ip_address"] or None
        report.arrival_at = parsed["arrival_at"]
        report.original_mail_from = parsed["original_mail_from"]
        report.original_rcpt_to = parsed["original_rcpt_to"]
        report.authentication_results = parsed["authentication_results"]
        report.delivery_result = parsed["delivery_result"]
        report.original_headers = parsed["original_headers"]
        report.status = DmarcFailureReport.Status.PARSED
        report.error = ""
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to parse DMARC failure report {report_pk}: {e}")
        report.status = DmarcFailureReport.Status.FAILED
        report.error = str(e)
    finally:
        if report.pk:
            report.save(
                update_fields=[
                    "source_ip_address",
                    "arrival_at",
                    "original_mail_from",
                    "original_rcpt_to",
                    "authentication_results",
                    "delivery_result",
                    "original_headers",
                    "status",
                    "error",
                ]
            )


@task
def evaluate_incoming_message(message_pk):
    """Evaluate DMARC for a single incoming message and store the result."""
    from mx.models import IncomingMessage

    message = IncomingMessage.objects.get(pk=message_pk)
    try:
        result = evaluate_dmarc(message)

        from domains.models import Domain

        domain = Domain.objects.root_for(result["header_from"]).first()
        evaluation = DmarcEvaluation(
            incoming_message=message,
            org=message.org,
            domain=domain,
            **result,
        )
        evaluation.save(force_insert=True)
    except (OSError, ValueError) as e:
        logger.error(f"Failed to evaluate message {message_pk}: {e}")
        return

    # Generate RUF report if the message failed DMARC (has its own error handling)
    if domain and evaluation.disposition != DmarcEvaluation.Disposition.NONE:
        generate_and_send_ruf(domain, evaluation)


@task
def generate_daily_rua_reports():
    """Generate and send daily DMARC RUA reports for all verified domains."""
    from datetime import timedelta

    from domains.models import Domain

    end_at = timezone.now()
    begin_at = end_at - timedelta(days=1)

    for domain in Domain.objects.filter(verified_at__isnull=False):
        try:
            generate_and_send_rua(domain, begin_at, end_at)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to generate RUA report for {domain.name}: {e}")
