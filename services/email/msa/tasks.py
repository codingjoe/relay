import datetime
import logging

import aiosmtplib
import dns.resolver
import httpx
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.tasks import task
from threadmill.retry import ExponentialBackoff

from services.email.mta.mta_sts import MtaStsPolicy
from services.email.spam import SpamAction, check_message
from services.email.tls import parse_peer_certificates

logger = logging.getLogger(__name__)


class MxHostsExhaustedError(Exception):
    """All MX hosts for a recipient domain failed to accept the message."""

    def __init__(self, domain):
        super().__init__(f"All MX hosts failed for {domain}")


class AmbiguousSenderDomainError(ValueError):
    """The sender domain does not resolve to a single root domain."""

    def __init__(self):
        super().__init__("Outgoing message sender domain is ambiguous")


class SenderDomainMismatchError(ValueError):
    """The sender domain does not match the resolved root domain."""

    def __init__(self):
        super().__init__("Outgoing message sender domain does not match")


@task
def deliver_message(message_id):
    """
    Deliver a queued outgoing message to its recipients.

    Drop the message instead when the org is suspended.
    """
    from .models import OutgoingMessage, Transmission

    message = OutgoingMessage.objects.select_related("domain", "org").get(pk=message_id)
    if message.org.suspended_at:
        message.status = OutgoingMessage.Status.DROPPED
        message.save(update_fields=["status", "modified_at"])
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            code=550,
            output="550 Account suspended due to sender reputation",
        )
        return

    try:
        send_outgoing_message(message)
    except Exception as e:  # storage backend raises varied exceptions
        logger.exception("Transmission error for message %r", message_id)
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            details=str(e),
        )
        message.status = OutgoingMessage.Status.FAILED
        message.save(update_fields=["status"])


def resolve_sender_domain(message):
    """Verify that the message's sender domain matches its root domain."""
    from domains.models import Domain, canonicalize_domain_name

    canonical_name = canonicalize_domain_name(message.domain.name)
    try:
        resolved_domain = Domain.objects.root_for(canonical_name, include_managed=True)
    except Domain.DoesNotExist as error:
        raise AmbiguousSenderDomainError from error
    if (
        resolved_domain.pk != message.domain.pk
        or resolved_domain.org_id != message.org_id
        or resolved_domain.name != canonical_name
    ):
        raise SenderDomainMismatchError


def send_outgoing_message(message):
    """Send the message via the recipient domain's MX hosts and record the outcome."""
    from .models import OutgoingMessage, Transmission

    resolve_sender_domain(message)
    raw_bytes = message.raw_body.read()
    return_path = (
        f"{settings.RELAY_BOUNCE_LOCAL_PART}+{message.id}"
        f"@{message.domain.sender_domain}"
    )
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
            response, tls_details = async_to_sync(send_via_mx)(
                raw_bytes,
                mx_host,
                return_path,
                [message.rcpt_to],
            )
        except aiosmtplib.SMTPResponseException as e:
            code = getattr(e, "code", getattr(e, "smtp_code", 0))
            if 400 <= code < 500:
                raise
            record_bounce(message, code, str(e), mx_host)
            return
        except aiosmtplib.SMTPException, OSError:
            pass
        else:
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.SENT,
                output=str(response),
                mx_host=mx_host,
                **tls_details,
            )
            message.status = OutgoingMessage.Status.SENT
            message.save(update_fields=["status"])
            return

    raise MxHostsExhaustedError(rcpt_domain)


def record_bounce(message, code, output, mx_host):
    """Record a permanent bounce and suppress the recipient address."""
    from .models import OutgoingMessage, SuppressionEntry, Transmission

    Transmission.objects.create(
        message=message,
        status=Transmission.Status.BOUNCED,
        code=code,
        output=output,
        mx_host=mx_host,
    )
    message.status = OutgoingMessage.Status.BOUNCED
    message.save(update_fields=["status"])
    SuppressionEntry.objects.create_or_update(
        org=message.org,
        email=message.rcpt_to,
        reason=SuppressionEntry.Reason.BOUNCE,
    )


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


async def send_via_mx(
    raw_bytes: bytes, mx_host: str, sender: str, recipients: list[str]
) -> tuple[str, dict]:
    """
    Deliver a message to an MX host over STARTTLS on port 25.

    Returns the SMTP response with the negotiated TLS details.
    """
    from kms.models import Certificate

    from .models import Transmission

    async with aiosmtplib.SMTP(
        hostname=mx_host,
        port=25,
        use_tls=False,
        start_tls=True,
        local_hostname=settings.RELAY_SMTP_PUBLIC_HOSTNAME,
    ) as smtp_client:
        response = await smtp_client.sendmail(sender, recipients, raw_bytes)
        # The server may drop the connection right after accepting, so the
        # transport reads must not fail a delivery that already succeeded.
        try:
            cipher = smtp_client.get_transport_info("cipher") or (None, None, None)
            ssl_object = smtp_client.get_transport_info("ssl_object")
            sockname = smtp_client.get_transport_info("sockname")
            peername = smtp_client.get_transport_info("peername")
        except aiosmtplib.SMTPServerDisconnected:
            cipher = (None, None, None)
            ssl_object = None
            sockname = None
            peername = None
    tls_details = {
        "tls_mode": Transmission.TlsMode.STARTTLS,
        "tls_cipher": cipher[0] or "",
        "tls_version": cipher[1] or "",
        "sending_mta_ip_address": sockname[0] if sockname else None,
        "receiving_mx_ip_address": peername[0] if peername else None,
    }
    if ssl_object is not None:
        tls_details["tls_certificate"] = await sync_to_async(
            Certificate.store_presented_chain
        )(parse_peer_certificates(ssl_object))
    return response, tls_details


@task(
    retry=ExponentialBackoff(
        base_delay=datetime.timedelta(seconds=1),
        max_delay=datetime.timedelta(minutes=5),
        max_retries=5,
        expected_exceptions=(httpx.HTTPError, OSError),
    )
)
def check_outgoing_spam(message_pk, client_ip):
    """
    Check an outgoing message for spam before delivery.

    Messages for suspended orgs are dropped without a spam check. Clean
    messages are enqueued for delivery.
    """
    from .models import OutgoingMessage

    message = OutgoingMessage.objects.select_related("org").get(pk=message_pk)
    if message.org.suspended_at:
        from .models import Transmission

        message.status = OutgoingMessage.Status.DROPPED
        message.save(update_fields=["status", "modified_at"])
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            code=550,
            output="550 Account suspended due to sender reputation",
        )
        return

    raw_bytes = message.raw_body.read()
    spam = async_to_sync(check_message)(raw_bytes, client_ip=client_ip)
    is_spam = (
        spam.action == SpamAction.REJECT
        or spam.score >= settings.RELAY_RSPAMD_HOLD_SCORE
    )
    message.spam_score = spam.score
    message.spam_action = spam.action
    if is_spam:
        message.status = OutgoingMessage.Status.HELD
    message.save(update_fields=["spam_score", "spam_action", "status"])
    if not is_spam:
        deliver_message.enqueue(message_id=str(message.pk))
