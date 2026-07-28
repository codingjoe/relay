"""Tasks for parsing DMARC reports."""

import logging
import xml.etree.ElementTree as ET

from django.tasks import task

from .models import DmarcFailureReport, DmarcRecord, DmarcReport
from .parser import extract_attachment, parse_arf, parse_dmarc_xml

logger = logging.getLogger(__name__)


@task
def parse_dmarc_report(report_pk):
    """Parse a received DMARC aggregate report and store its records."""
    report = DmarcReport.objects.get(pk=report_pk)
    try:
        raw_bytes = report.raw_body.read()
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
        report.report_status = DmarcReport.Status.PARSED
        report.error = ""
    except (OSError, ValueError, ET.ParseError) as e:
        logger.error(f"Failed to parse DMARC report {report_pk}: {e}")
        report.report_status = DmarcReport.Status.FAILED
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
                    "report_status",
                    "error",
                ]
            )


@task
def parse_dmarc_failure_report(report_pk):
    """Parse a received DMARC forensic (RUF) report."""
    report = DmarcFailureReport.objects.get(pk=report_pk)
    try:
        raw_bytes = report.raw_body.read()
        parsed = parse_arf(raw_bytes)

        report.source_ip_address = parsed["source_ip_address"] or None
        report.arrival_at = parsed["arrival_at"]
        report.original_mail_from = parsed["original_mail_from"]
        report.original_rcpt_to = parsed["original_rcpt_to"]
        report.authentication_results = parsed["authentication_results"]
        report.delivery_result = parsed["delivery_result"]
        report.original_headers = parsed["original_headers"]
        report.report_status = DmarcFailureReport.Status.PARSED
        report.error = ""
    except (OSError, ValueError) as e:
        logger.error(f"Failed to parse DMARC failure report {report_pk}: {e}")
        report.report_status = DmarcFailureReport.Status.FAILED
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
                    "report_status",
                    "error",
                ]
            )
