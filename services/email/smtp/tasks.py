import asyncio
import logging

import aiosmtplib
import dns.resolver
from django.conf import settings
from django.core.files.base import ContentFile
from django.tasks import task

from services.email.mx.mta_sts import MtaStsPolicy

logger = logging.getLogger(__name__)


class MxHostsExhausted(Exception):
    """All MX hosts for a recipient domain failed to accept the message."""


@task
def deliver_message(message_id):
    """Deliver a queued outgoing message to its recipients."""
    from .models import OutgoingMessage, SuppressionEntry, Transmission

    message = OutgoingMessage.objects.select_related("domain").get(pk=message_id)

    try:
        if message.domain is None:
            raise ValueError("Outgoing message has no sender domain")

        from domains.models import Domain, canonicalize_domain_name

        canonical_name = canonicalize_domain_name(message.domain.name)
        try:
            resolved_domain = Domain.objects.root_for(
                canonical_name,
                include_managed=True,
            )
        except Domain.DoesNotExist as error:
            raise ValueError("Outgoing message sender domain is ambiguous") from error
        if (
            resolved_domain.pk != message.domain.pk
            or resolved_domain.org_id != message.org_id
            or resolved_domain.name != canonical_name
        ):
            raise ValueError("Outgoing message sender domain does not match")

        raw_bytes = message.raw_body.read()
        from domains.dkim import sign_message

        raw_bytes = sign_message(raw_bytes, message.domain)
        return_path = (
            f"{settings.RELAY_BOUNCE_LOCAL_PART}+{message.id}"
            f"@{message.domain.sender_domain}"
        )
        message.raw_body.save(
            message.raw_body.name.split("/")[-1],
            ContentFile(raw_bytes),
            save=False,
        )
        message.save(update_fields=["raw_body"])

        rcpt_domain = message.rcpt_to.split("@")[-1]
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
                    message.rcpt_to,
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
                        local_hostname=settings.RELAY_SMTP_PUBLIC_HOSTNAME,
                        sender=return_path,
                        recipients=[message.rcpt_to],
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
                SuppressionEntry.objects.create_or_update(
                    org=message.org,
                    email=message.rcpt_to,
                    reason=SuppressionEntry.Reason.BOUNCE,
                )
                return
            except aiosmtplib.SMTPException, OSError:
                pass

        raise MxHostsExhausted(f"All MX hosts failed for {rcpt_domain}")

    except Exception as e:  # noqa: BLE001  # storage backend raises varied exceptions
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
