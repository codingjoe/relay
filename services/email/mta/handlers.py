import logging
import re
from email import message_from_bytes
from email.utils import formatdate

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from abstract.email_utils import decode_header_value
from abstract.mailauth import Disposition, DmarcEvaluation
from abstract.signals import request_scoped
from domains.models import Domain
from services.email.message.models import Transmission
from services.email.proxy_protocol import ProxyProtocolMixin, get_client_ip

from .arc import seal_message
from .models import (
    IncomingMessage,
    TlsReport,
)
from .signals import fbl_report_received, report_received
from .tasks import check_incoming_spam, notify_postmaster_recipients, parse_tls_report

logger = logging.getLogger(__name__)

# HELO names are attacker-controlled; only these characters may reach the
# Received header so they cannot inject header lines or Received clauses.
HELO_ALLOWED_CHARS = re.compile(r"[A-Za-z0-9.\-:\[\]]")


def received_header(session) -> bytes:
    """
    Return the Received header line for an inbound message (RFC 5321 §4.4).

    The HELO name is reduced to a safe charset so it cannot inject header
    lines or Received clauses.
    """
    helo = "".join(HELO_ALLOWED_CHARS.findall(getattr(session, "host_name", "") or ""))
    protocol = "ESMTPS" if getattr(session, "ssl", None) else "ESMTP"
    received = f"from {helo or 'unknown'}"
    if ip := get_client_ip(session):
        received += f" ([{ip}])"
    received += (
        f"\r\n\tby {settings.RELAY_DNS_MX_HOSTNAMES[0]} with {protocol};\r\n\t"
        + formatdate(usegmt=True)
    )
    return f"Received: {received}".encode()


class MXHandler(ProxyProtocolMixin):
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        rcpt_domain = address.split("@")[-1] if "@" in address else ""
        try:
            domain = await sync_to_async(
                Domain.objects.select_related("dkim_key_rsa2048").root_for
            )(rcpt_domain, include_managed=True)
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
        domain = envelope.recipient_domain
        evaluation = await sync_to_async(
            DmarcEvaluation.from_bytes, thread_sensitive=False
        )(raw_bytes, mail_from, client_ip)
        if evaluation.disposition == Disposition.REJECT:
            return "550 Message rejected by DMARC policy"
        status = (
            IncomingMessage.Status.QUARANTINED
            if evaluation.disposition == Disposition.QUARANTINE
            else IncomingMessage.Status.RECEIVED
        )
        raw_bytes = received_header(session) + b"\r\n" + raw_bytes
        raw_bytes = await sync_to_async(seal_message, thread_sensitive=False)(
            raw_bytes, evaluation, domain
        )
        result = await process_incoming_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            getattr(session, "ssl", None),
            domain,
            status,
            client_ip,
        )
        logger.info("Incoming message from %r to %r: %r", mail_from, rcpt_to, result)
        return result


@sync_to_async
@request_scoped
def process_incoming_message(
    mail_from, rcpt_to, raw_bytes, tls, domain, status, client_ip
):
    msg = message_from_bytes(raw_bytes)
    rcpt_domain = rcpt_to.split("@")[-1] if "@" in rcpt_to else ""
    local_part = rcpt_to.split("@", 1)[0].lower() if "@" in rcpt_to else ""
    subject = decode_header_value(msg.get("Subject", ""))
    message_id = msg.get("Message-ID", "")
    started_at = timezone.now()

    match local_part:
        case (
            settings.RELAY_DMARC_REPORT_LOCAL_PART | settings.RELAY_DMARC_RUF_LOCAL_PART
        ):
            # DMARC reports belong to the dmarc app; dispatch via signal so
            # mta does not depend on it.
            responses = report_received.send(
                sender=IncomingMessage,
                local_part=local_part,
                domain=domain,
                receiving_domain=rcpt_domain,
                mail_from=mail_from,
                rcpt_to=rcpt_to,
                subject=subject,
                message_id=message_id,
                raw_bytes=raw_bytes,
                tls=tls,
                client_ip=client_ip,
                started_at=started_at,
            )
            if any(r is not None for _, r in responses):
                return "250 OK"

        case settings.RELAY_TLS_REPORT_LOCAL_PART:
            with Transmission.record_reception(tls, started_at, client_ip) as reception:
                reception.message = report = TlsReport.objects.create(
                    org=domain.org,
                    domain=domain,
                    receiving_domain=rcpt_domain,
                    mail_from=mail_from,
                    rcpt_to=rcpt_to,
                    subject=subject,
                    message_id=message_id,
                    report_id="",
                    headers=TlsReport.headers_from_raw(raw_bytes),
                    raw_body=SimpleUploadedFile(
                        f"{message_id or 'message'}.eml", raw_bytes
                    ),
                )
            transaction.on_commit(
                lambda: parse_tls_report.enqueue(report_pk=str(report.pk))
            )
            return "250 OK"

        case _ if (
            rcpt_to.lower().rstrip(".") == settings.RELAY_FBL_ADDRESS
            and mail_from.lower() in settings.RELAY_FBL_SENDERS
        ):
            with Transmission.record_reception(tls, started_at, client_ip) as reception:
                reception.message = message = IncomingMessage.objects.create(
                    org=domain.org,
                    domain=domain,
                    receiving_domain=rcpt_domain,
                    mail_from=mail_from,
                    rcpt_to=rcpt_to,
                    subject=subject,
                    message_id=message_id,
                    status=status,
                    headers=IncomingMessage.headers_from_raw(raw_bytes),
                    raw_body=SimpleUploadedFile(
                        f"{message_id or 'message'}.eml", raw_bytes
                    ),
                )
            fbl_report_received.send(sender=IncomingMessage, message=message)
            return "250 OK"

    is_postmaster_recipient = local_part == settings.RELAY_POSTMASTER_LOCAL_PART or (
        local_part.startswith(f"{settings.RELAY_POSTMASTER_LOCAL_PART}+")
    )
    with Transmission.record_reception(tls, started_at, client_ip) as reception:
        reception.message = message = IncomingMessage.objects.create(
            org=domain.org,
            domain=domain,
            receiving_domain=rcpt_domain,
            mail_from=mail_from,
            rcpt_to=rcpt_to,
            subject=subject,
            message_id=message_id,
            status=status,
            headers=IncomingMessage.headers_from_raw(raw_bytes),
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
