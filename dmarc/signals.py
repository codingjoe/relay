"""Signal handlers for DMARC and TLS-RPT report ingestion."""

import uuid

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from domains.models import Domain

from .models import DmarcReport, TlsReport
from .tasks import parse_dmarc_report, parse_tls_report


@receiver(post_save, sender="mx.IncomingMessage")
def handle_incoming_message(sender, instance, created, **kwargs):
    """Create a report stub when a report email arrives as an IncomingMessage."""
    if not created:
        return

    local_part = (
        instance.rcpt_to.split("@", 1)[0].lower() if "@" in instance.rcpt_to else ""
    )
    match local_part:
        case settings.RELAY_DMARC_REPORT_LOCAL_PART:
            domain = Domain.objects.root_for(instance.receiving_domain).first()
            report = DmarcReport.objects.create(
                org=instance.org,
                domain=domain,
                incoming_message=instance,
                report_id=str(uuid.uuid7()),
                status=DmarcReport.Status.RECEIVED,
            )
            transaction.on_commit(
                lambda: parse_dmarc_report.enqueue(report_pk=report.pk)
            )
        case settings.RELAY_TLS_REPORT_LOCAL_PART:
            domain = Domain.objects.root_for(instance.receiving_domain).first()
            report = TlsReport.objects.create(
                org=instance.org,
                domain=domain,
                incoming_message=instance,
                report_id=str(uuid.uuid7()),
                status=TlsReport.Status.RECEIVED,
            )
            transaction.on_commit(lambda: parse_tls_report.enqueue(report_pk=report.pk))
