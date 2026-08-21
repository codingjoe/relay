import logging
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction

from domains.models import Domain
from services.email.proxy import ProxyProtocolMixin
from services.email.spam import SpamResult, check_message

from .models import IncomingMessage, TlsReport
from .tasks import dispatch_webhook, notify_postmaster_recipients, parse_tls_report

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
        local_part = rcpt_to.split("@", 1)[0].lower() if "@" in rcpt_to else ""
        report_local_parts = {
            settings.RELAY_DMARC_REPORT_LOCAL_PART,
            settings.RELAY_TLS_REPORT_LOCAL_PART,
            settings.RELAY_DMARC_RUF_LOCAL_PART,
        }
        if local_part in report_local_parts:
            spam = SpamResult()
        else:
            client_ip = session.peer[0] if session.peer else ""
            spam = await check_message(raw_bytes, client_ip=client_ip)
        result = await process_incoming_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            getattr(session, "ssl", False),
            getattr(envelope, "recipient_domain", None),
            spam,
        )
        logger.info(f"Incoming message from {mail_from} to {rcpt_to}: {result}")
        return result


@sync_to_async
def process_incoming_message(mail_from, rcpt_to, raw_bytes, tls, domain, spam):
    from services.email.dmarc.tasks import evaluate_incoming_message

    msg = message_from_bytes(raw_bytes)
    rcpt_domain = rcpt_to.split("@")[-1] if "@" in rcpt_to else ""
    local_part = rcpt_to.split("@", 1)[0].lower() if "@" in rcpt_to else ""

    match local_part:
        case settings.RELAY_DMARC_REPORT_LOCAL_PART:
            from services.email.dmarc.models import DmarcReport
            from services.email.dmarc.tasks import parse_dmarc_report

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
            from services.email.dmarc.models import DmarcFailureReport
            from services.email.dmarc.tasks import parse_dmarc_failure_report

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

    is_postmaster_recipient = local_part == settings.RELAY_POSTMASTER_LOCAL_PART or (
        local_part.startswith(f"{settings.RELAY_POSTMASTER_LOCAL_PART}+")
    )
    is_bounce_recipient = local_part.startswith(f"{settings.RELAY_BOUNCE_LOCAL_PART}+")

    if (
        not is_postmaster_recipient
        and not is_bounce_recipient
        and not domain.org.billing_is_active
        and not domain.org.members.filter(email__iexact=mail_from).exists()
    ):
        return "550 Sender not allowed without active billing"

    is_spam = (
        spam.action == "reject" or spam.score >= settings.RELAY_RSPAMD_REJECT_SCORE
    )
    status = (
        IncomingMessage.Status.QUARANTINED
        if is_spam
        else IncomingMessage.Status.RECEIVED
    )
    message = IncomingMessage(
        org=domain.org,
        domain=domain,
        receiving_domain=rcpt_domain,
        mail_from=mail_from,
        rcpt_to=rcpt_to,
        subject=msg.get("Subject", ""),
        message_id=msg.get("Message-ID", ""),
        received_with_tls=bool(tls),
        status=status,
        spam_score=spam.score,
        spam_action=spam.action,
    )
    message.raw_body.save(
        f"{message.id}.eml",
        ContentFile(spam.add_headers(raw_bytes)),
        save=False,
    )
    message.save(force_insert=True)
    transaction.on_commit(
        lambda: evaluate_incoming_message.enqueue(message_pk=str(message.id))
    )
    if not is_spam:
        transaction.on_commit(
            lambda: dispatch_webhook.enqueue(message_id=str(message.id))
        )
    if is_postmaster_recipient:
        transaction.on_commit(
            lambda: notify_postmaster_recipients.enqueue(message_pk=str(message.id))
        )
    return "250 OK"
