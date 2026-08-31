import logging
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction

from abstract.mailauth import Disposition, DmarcEvaluation
from domains.models import Domain
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.dmarc.tasks import (
    parse_dmarc_failure_report,
    parse_dmarc_report,
)
from services.email.proxy_protocol import ProxyProtocolMixin, get_client_ip

from .models import (
    IncomingMessage,
    TlsReport,
)
from .signals import fbl_report_received
from .tasks import check_incoming_spam, notify_postmaster_recipients, parse_tls_report

logger = logging.getLogger(__name__)


class MXHandler(ProxyProtocolMixin):
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        rcpt_domain = address.split("@")[-1] if "@" in address else ""
        try:
            domain = await sync_to_async(Domain.objects.root_for)(
                rcpt_domain,
                include_managed=True,
            )
        except Domain.DoesNotExist:
            return "550 Relay not authorised for this recipient"
        envelope.rcpt_tos.append(address)
        if not hasattr(envelope, "recipient_domain"):
            envelope.recipient_domain = domain
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        mail_from = envelope.mail_from or ""
        rcpt_to = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        raw_data = envelope.content
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        client_ip = get_client_ip(session)
        evaluation = await sync_to_async(
            DmarcEvaluation.from_bytes, thread_sensitive=False
        )(raw_bytes, mail_from)
        if evaluation.disposition == Disposition.REJECT:
            return "550 Message rejected by DMARC policy"
        status = (
            IncomingMessage.Status.QUARANTINED
            if evaluation.disposition == Disposition.QUARANTINE
            else IncomingMessage.Status.RECEIVED
        )
        result = await process_incoming_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            getattr(session, "ssl", False),
            getattr(envelope, "recipient_domain", None),
            status,
            client_ip,
        )
        logger.info(f"Incoming message from {mail_from} to {rcpt_to}: {result}")
        return result


@sync_to_async
def process_incoming_message(
    mail_from, rcpt_to, raw_bytes, tls, domain, status, client_ip
):
    msg = message_from_bytes(raw_bytes)
    rcpt_domain = rcpt_to.split("@")[-1] if "@" in rcpt_to else ""
    local_part = rcpt_to.split("@", 1)[0].lower() if "@" in rcpt_to else ""
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")

    match local_part:
        case settings.RELAY_DMARC_REPORT_LOCAL_PART:
            report = DmarcReport.objects.create(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=subject,
                message_id=message_id,
                received_with_tls=bool(tls),
                report_id="",
                raw_body=SimpleUploadedFile(
                    f"{message_id or 'message'}.eml", raw_bytes
                ),
            )
            transaction.on_commit(
                lambda: parse_dmarc_report.enqueue(report_pk=str(report.pk))
            )
            return "250 OK"

        case settings.RELAY_TLS_REPORT_LOCAL_PART:
            report = TlsReport.objects.create(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=subject,
                message_id=message_id,
                received_with_tls=bool(tls),
                report_id="",
                raw_body=SimpleUploadedFile(
                    f"{message_id or 'message'}.eml", raw_bytes
                ),
            )
            transaction.on_commit(
                lambda: parse_tls_report.enqueue(report_pk=str(report.pk))
            )
            return "250 OK"

        case settings.RELAY_DMARC_RUF_LOCAL_PART:
            report = DmarcFailureReport.objects.create(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=subject,
                message_id=message_id,
                received_with_tls=bool(tls),
                raw_body=SimpleUploadedFile(
                    f"{message_id or 'message'}.eml", raw_bytes
                ),
            )
            transaction.on_commit(
                lambda: parse_dmarc_failure_report.enqueue(report_pk=str(report.pk))
            )
            return "250 OK"

        case _ if (
            rcpt_to.lower().rstrip(".") == settings.RELAY_FBL_ADDRESS
            and mail_from.lower() in settings.RELAY_FBL_SENDERS
        ):
            message = IncomingMessage.objects.create(
                org=domain.org,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=subject,
                message_id=message_id,
                received_with_tls=bool(tls),
                status=status,
                raw_body=SimpleUploadedFile(
                    f"{message_id or 'message'}.eml", raw_bytes
                ),
            )
            fbl_report_received.send(sender=IncomingMessage, message=message)
            return "250 OK"

    is_postmaster_recipient = local_part == settings.RELAY_POSTMASTER_LOCAL_PART or (
        local_part.startswith(f"{settings.RELAY_POSTMASTER_LOCAL_PART}+")
    )
    message = IncomingMessage.objects.create(
        org=domain.org,
        domain=domain,
        receiving_domain=rcpt_domain,
        mail_from=mail_from,
        rcpt_to=rcpt_to,
        subject=subject,
        message_id=message_id,
        received_with_tls=bool(tls),
        status=status,
        raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
    )
    transaction.on_commit(
        lambda: check_incoming_spam.enqueue(
            message_pk=str(message.id), client_ip=client_ip
        )
    )
    if is_postmaster_recipient:
        transaction.on_commit(
            lambda: notify_postmaster_recipients.enqueue(message_pk=str(message.id))
        )
    return "250 OK"
