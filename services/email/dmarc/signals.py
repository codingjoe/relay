import logging

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.dispatch import receiver

from services.email.mta.signals import report_received

from .models import DmarcFailureReport, DmarcReport
from .tasks import parse_dmarc_failure_report, parse_dmarc_report

logger = logging.getLogger(__name__)


@receiver(report_received, dispatch_uid="dmarc_create_report")
def create_report(
    sender,
    local_part,
    domain,
    mail_from,
    rcpt_to,
    subject,
    message_id,
    raw_bytes,
    tls_fields,
    **kwargs,
):
    """Create a DMARC report from an incoming report email."""
    if local_part == settings.RELAY_DMARC_REPORT_LOCAL_PART:
        report = DmarcReport.objects.create(
            org=domain.org,
            domain=domain,
            receiving_domain=rcpt_to.split("@")[-1] if "@" in rcpt_to else "",
            mail_from=mail_from,
            rcpt_to=rcpt_to,
            subject=subject,
            message_id=message_id,
            report_id="",
            headers=DmarcReport.headers_from_raw(raw_bytes),
            raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
            **tls_fields,
        )
        parse_task = parse_dmarc_report
    else:
        report = DmarcFailureReport.objects.create(
            org=domain.org,
            domain=domain,
            receiving_domain=rcpt_to.split("@")[-1] if "@" in rcpt_to else "",
            mail_from=mail_from,
            rcpt_to=rcpt_to,
            subject=subject,
            message_id=message_id,
            headers=DmarcFailureReport.headers_from_raw(raw_bytes),
            raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
            **tls_fields,
        )
        parse_task = parse_dmarc_failure_report
    transaction.on_commit(lambda: parse_task.enqueue(report_pk=str(report.pk)))
    logger.info("Stored %s from %r", report._meta.verbose_name, mail_from)
    return "250 OK"
