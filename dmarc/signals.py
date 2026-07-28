"""Signal handlers for DMARC report ingestion and evaluation."""

import uuid

from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from domains.models import Domain

from .models import DmarcFailureReport, DmarcReport
from .tasks import (
    evaluate_incoming_message,
    parse_dmarc_failure_report,
    parse_dmarc_report,
)


@receiver(post_save, sender="mx.IncomingMessage")
def handle_incoming_message(sender, instance, created, **kwargs):
    """Create a report stub or evaluate DMARC when an email arrives."""
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
        case settings.RELAY_DMARC_RUF_LOCAL_PART:
            domain = Domain.objects.root_for(instance.receiving_domain).first()
            report = DmarcFailureReport.objects.create(
                org=instance.org,
                domain=domain,
                incoming_message=instance,
                status=DmarcFailureReport.Status.RECEIVED,
            )
            transaction.on_commit(
                lambda: parse_dmarc_failure_report.enqueue(report_pk=report.pk)
            )
        case _:
            # Non-report messages: evaluate DMARC
            transaction.on_commit(
                lambda: evaluate_incoming_message.enqueue(message_pk=instance.pk)
            )
