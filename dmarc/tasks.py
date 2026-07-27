"""Tasks for parsing DMARC and TLS-RPT reports."""

import logging

from django.tasks import task

from .models import DmarcRecord, DmarcReport, TlsFailure, TlsReport
from .parser import extract_attachment, parse_dmarc_xml, parse_tls_json

logger = logging.getLogger(__name__)


@task
def parse_dmarc_report(report_pk):
    """Parse a received DMARC aggregate report and store its records."""
    report = DmarcReport.objects.get(pk=report_pk)
    try:
        raw_bytes = report.raw_email.read()
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
def parse_tls_report(report_pk):
    """Parse a received TLS-RPT report and store its failures."""
    report = TlsReport.objects.get(pk=report_pk)
    try:
        raw_bytes = report.raw_email.read()
        data = extract_attachment(raw_bytes)
        if data is None:
            raise ValueError("No attachment found in TLS-RPT report email.")
        parsed = parse_tls_json(data)
        meta = parsed["metadata"]

        # Check for a duplicate (already-parsed report with same domain + report_id).
        if (
            meta["report_id"]
            and TlsReport.objects.filter(
                domain=report.domain, report_id=meta["report_id"]
            )
            .exclude(pk=report.pk)
            .exists()
        ):
            logger.info(f"Duplicate TLS-RPT report {report_pk}, discarding.")
            report.delete()
            return

        report.reporting_org = meta["reporting_org"]
        report.reporting_email = meta["reporting_email"]
        report.report_id = meta["report_id"]
        report.begin_at = meta["begin_at"]
        report.end_at = meta["end_at"]

        failures = []
        total_successful = 0
        total_failed = 0
        for policy in parsed["policies"]:
            total_successful += policy["successful_session_count"]
            total_failed += policy["failed_session_count"]
            for failure_data in policy["failures"]:
                failure_data["policy_type"] = policy["policy_type"]
                failure_data["policy_domain"] = policy["policy_domain"]
                failures.append(TlsFailure(report=report, **failure_data))

        report.successful_session_count = total_successful
        report.failed_session_count = total_failed

        TlsFailure.objects.bulk_create(failures)
        report.status = TlsReport.Status.PARSED
        report.error = ""
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to parse TLS-RPT report {report_pk}: {e}")
        report.status = TlsReport.Status.FAILED
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
                    "successful_session_count",
                    "failed_session_count",
                    "status",
                    "error",
                ]
            )
