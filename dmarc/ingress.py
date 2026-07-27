"""Create report stubs from incoming report emails and enqueue parsing."""

import uuid

from django.core.files.base import ContentFile

from .models import DmarcReport, TlsReport
from .tasks import parse_dmarc_report, parse_tls_report


def create_dmarc_report(domain, mail_from, rcpt_to, raw_bytes):
    """Store a raw DMARC report email and enqueue parsing.

    Returns an SMTP response string (250 on success, 451 on storage failure).
    """
    try:
        report = DmarcReport(
            org=domain.org,
            domain=domain,
            report_id=str(uuid.uuid7()),
            status=DmarcReport.Status.RECEIVED,
        )
        report.raw_email.save(
            f"{uuid.uuid7()}.eml",
            ContentFile(raw_bytes),
            save=False,
        )
        report.save(force_insert=True)
        parse_dmarc_report.enqueue(report_pk=report.pk)
        return "250 OK"
    except OSError, ValueError:
        return "451 Requested action aborted: local error"


def create_tls_report(domain, mail_from, rcpt_to, raw_bytes):
    """Store a raw TLS-RPT report email and enqueue parsing.

    Returns an SMTP response string (250 on success, 451 on storage failure).
    """
    try:
        report = TlsReport(
            org=domain.org,
            domain=domain,
            report_id=str(uuid.uuid7()),
            status=TlsReport.Status.RECEIVED,
        )
        report.raw_email.save(
            f"{uuid.uuid7()}.eml",
            ContentFile(raw_bytes),
            save=False,
        )
        report.save(force_insert=True)
        parse_tls_report.enqueue(report_pk=report.pk)
        return "250 OK"
    except OSError, ValueError:
        return "451 Requested action aborted: local error"
