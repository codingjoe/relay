import logging
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from domains.models import Domain

from .models import IncomingMessage, TlsReport
from .tasks import dispatch_webhook, parse_tls_report

logger = logging.getLogger(__name__)


class MXHandler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        mail_from = envelope.mail_from or ""
        rcpt_to = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        raw_data = envelope.content
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        result = await process_incoming_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            getattr(session, "ssl", False),
        )
        logger.info(f"Incoming message from {mail_from} to {rcpt_to}: {result}")
        return result


@sync_to_async
def process_incoming_message(mail_from, rcpt_to, raw_bytes, tls):
    msg = message_from_bytes(raw_bytes)
    rcpt_domain = rcpt_to.split("@")[-1] if "@" in rcpt_to else ""
    local_part = rcpt_to.split("@", 1)[0].lower() if "@" in rcpt_to else ""

    try:
        domain = Domain.objects.root_for(rcpt_domain)
    except Domain.DoesNotExist:
        return "550 Relay not authorised for this recipient"

    match local_part:
        case settings.RELAY_DMARC_REPORT_LOCAL_PART:
            from dmarc.models import DmarcReport
            from dmarc.tasks import parse_dmarc_report

            report = DmarcReport(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=msg.get("Subject", ""),
                message_id=msg.get("Message-ID", ""),
                received_with_tls=bool(tls),
                report_id="",
            )
            report.raw_body.save(f"{report.id}.eml", ContentFile(raw_bytes), save=False)
            report.save(force_insert=True)
            transaction.on_commit(
                lambda: parse_dmarc_report.enqueue(report_pk=report.pk)
            )
            return "250 OK"

        case settings.RELAY_TLS_REPORT_LOCAL_PART:
            report = TlsReport(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=msg.get("Subject", ""),
                message_id=msg.get("Message-ID", ""),
                received_with_tls=bool(tls),
                report_id="",
            )
            report.raw_body.save(f"{report.id}.eml", ContentFile(raw_bytes), save=False)
            report.save(force_insert=True)
            transaction.on_commit(lambda: parse_tls_report.enqueue(report_pk=report.pk))
            return "250 OK"

        case settings.RELAY_DMARC_RUF_LOCAL_PART:
            from dmarc.models import DmarcFailureReport
            from dmarc.tasks import parse_dmarc_failure_report

            report = DmarcFailureReport(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=msg.get("Subject", ""),
                message_id=msg.get("Message-ID", ""),
                received_with_tls=bool(tls),
            )
            report.raw_body.save(f"{report.id}.eml", ContentFile(raw_bytes), save=False)
            report.save(force_insert=True)
            transaction.on_commit(
                lambda: parse_dmarc_failure_report.enqueue(report_pk=report.pk)
            )
            return "250 OK"

    message = IncomingMessage(
        org=domain.org,
        receiving_domain=rcpt_domain,
        mail_from=mail_from,
        rcpt_to=rcpt_to,
        subject=msg.get("Subject", ""),
        message_id=msg.get("Message-ID", ""),
        received_with_tls=bool(tls),
        status=IncomingMessage.Status.RECEIVED,
    )
    message.raw_body.save(f"{message.id}.eml", ContentFile(raw_bytes), save=False)
    message.save(force_insert=True)
    transaction.on_commit(lambda: dispatch_webhook.enqueue(message_id=str(message.id)))
    transaction.on_commit(lambda: enqueue_dmarc_evaluation(message))
    return "250 OK"


def enqueue_dmarc_evaluation(message):
    from dmarc.tasks import evaluate_incoming_message

    evaluate_incoming_message.enqueue(message_pk=str(message.id))
