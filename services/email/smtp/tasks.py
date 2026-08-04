"""Outgoing message delivery tasks."""

import asyncio
import logging

import aiosmtplib
import dns.resolver
from django.core.files.base import ContentFile
from django.tasks import task

from services.email.mx.mta_sts import MtaStsPolicy

from .models import OutgoingMessage, SuppressionEntry, Transmission

logger = logging.getLogger(__name__)


class MxHostsExhausted(Exception):
    """All MX hosts for a recipient domain failed to accept the message."""


@task
def deliver_message(message_id, rcpt_to, mail_from, domain_id=None):
    """Deliver a queued outgoing message to its recipients."""
    message = OutgoingMessage.objects.get(pk=message_id)

    try:
        raw_bytes = message.raw_body.read()

        if domain_id:
            from domains.dkim import sign_message
            from domains.models import Domain

            raw_bytes = sign_message(raw_bytes, Domain.objects.get(pk=domain_id))
            message.raw_body.save(
                message.raw_body.name.split("/")[-1],
                ContentFile(raw_bytes),
                save=False,
            )
            message.save(update_fields=["raw_body"])

        rcpt_domain = rcpt_to.split("@")[-1]
        mx_hosts = fetch_mx_hosts(rcpt_domain)

        if not mx_hosts:
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.FAILED,
                details=f"No MX records found for {rcpt_domain}",
            )
            message.status = OutgoingMessage.Status.FAILED
            message.save(update_fields=["status"])
            return

        for mx_host in mx_hosts:
            allowed, reason = MtaStsPolicy.get(rcpt_domain).allows(mx_host)
            if not allowed:
                logger.warning(
                    "MTA-STS blocked delivery to %s via %s: %s",
                    rcpt_to,
                    mx_host,
                    reason,
                )
                continue
            try:
                response = asyncio.run(
                    aiosmtplib.send(
                        raw_bytes,
                        hostname=mx_host,
                        port=25,
                        use_tls=False,
                        start_tls=True,
                        sender=mail_from,
                        recipients=[rcpt_to],
                    )
                )
                Transmission.objects.create(
                    message=message,
                    status=Transmission.Status.SENT,
                    output=str(response),
                    sent_with_ssl=True,
                    log_id=str(response)[:255] if response else "",
                )
                message.status = OutgoingMessage.Status.SENT
                message.save(update_fields=["status"])
                return
            except aiosmtplib.SMTPResponseException as e:
                code = getattr(e, "code", getattr(e, "smtp_code", 0))
                if 400 <= code < 500:
                    raise
                Transmission.objects.create(
                    message=message,
                    status=Transmission.Status.BOUNCED,
                    code=code,
                    output=str(e),
                )
                message.status = OutgoingMessage.Status.BOUNCED
                message.save(update_fields=["status"])
                SuppressionEntry.objects.add(
                    message.org, rcpt_to, reason=SuppressionEntry.Reason.BOUNCE
                )
                return
            except aiosmtplib.SMTPException, OSError:
                continue

        raise MxHostsExhausted(f"All MX hosts failed for {rcpt_domain}")

    except Exception as e:  # noqa: BLE001 — storage backend raises varied exceptions
        logger.error(f"Transmission error for message {message_id}: {e}")
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            details=str(e),
        )
        message.status = OutgoingMessage.Status.FAILED
        message.save(update_fields=["status"])


def fetch_mx_hosts(domain):
    """Fetch MX records for a domain."""
    try:
        records = dns.resolver.resolve(domain, "MX")
        return [
            str(r.exchange).rstrip(".")
            for r in sorted(records, key=lambda r: r.preference)
        ]
    except dns.exception.DNSException:
        return []
