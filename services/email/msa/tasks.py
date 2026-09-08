import base64
import datetime
import hmac
import logging
import re
import uuid
from dataclasses import dataclass
from email import message_from_bytes
from email.utils import parseaddr

import aiosmtplib
import dns.resolver
import httpx
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.tasks import task
from threadmill.retry import ExponentialBackoff

from services.email.mta.models import IncomingMessage
from services.email.mta_sts import MtaStsPolicy
from services.email.spam import SpamAction, check_message
from services.email.tls import parse_peer_certificates

from .models import OutgoingMessage, SuppressionEntry, Transmission

logger = logging.getLogger(__name__)

bounce_signer = signing.Signer(salt="relay.bounce", sep=".", algorithm="sha256")


def mint_bounce_address(message: OutgoingMessage, key: str | None = None) -> str:
    """Return the signed VERP envelope sender address for a message."""
    value = base64.urlsafe_b64encode(message.pk.bytes).rstrip(b"=").decode()
    signature = bounce_signer.signature(value, key=key)[:20]
    return (
        f"{settings.RELAY_BOUNCE_LOCAL_PART}+{value}.{signature}"
        f"@{message.domain.sender_domain}"
    )


class MxHostsExhaustedError(Exception):
    """All MX hosts for a recipient domain failed to accept the message."""

    def __init__(self, domain):
        super().__init__(f"All MX hosts failed for {domain}")


class MissingDeliveryStatusPartError(ValueError):
    """The DSN has no message/delivery-status part."""

    def __init__(self):
        super().__init__("Message has no message/delivery-status part.")


class MissingRecipientBlockError(ValueError):
    """The delivery status part has no per-recipient block."""

    def __init__(self):
        super().__init__("Delivery status part has no per-recipient block.")


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
    return_path = mint_bounce_address(message)
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


@dataclass(frozen=True, slots=True)
class DeliveryStatus:
    """Per-recipient delivery status fields parsed from a DSN email."""

    action: str
    code: int | None
    output: str
    final_recipient: str


def parse_delivery_status(raw_bytes: bytes) -> DeliveryStatus:
    """
    Return the delivery status parsed from a DSN's first recipient block.

    Raise `ValueError` when the message has no `message/delivery-status`
    part or no per-recipient block.
    """
    msg = message_from_bytes(raw_bytes)
    status_part = next(
        (
            part
            for part in msg.walk()
            if part.get_content_type() == "message/delivery-status"
        ),
        None,
    )
    if status_part is None:
        raise MissingDeliveryStatusPartError
    recipient_blocks = [
        block
        for block in status_part.get_payload()
        if block.get("Action") or block.get("Final-Recipient")
    ]
    if not recipient_blocks:
        raise MissingRecipientBlockError
    recipient = recipient_blocks[0]
    # compat32 surfaces 8-bit header values as Header objects
    action = str(recipient.get("Action", ""))
    diagnostic_code = str(recipient.get("Diagnostic-Code", ""))
    status = str(recipient.get("Status", ""))
    final_recipient = str(
        recipient.get("Final-Recipient") or recipient.get("Original-Recipient") or ""
    )
    diagnostic_type, _, diagnostic_text = diagnostic_code.partition(";")
    match (
        re.search(r"\b[245]\d{2}\b", diagnostic_text)
        if diagnostic_type.strip().lower() == "smtp"
        else None
    ):
        case None:
            status_class = status.partition(".")[0]
            code = int(status_class) * 100 if status_class in ("2", "4", "5") else None
        case smtp_code:
            code = int(smtp_code.group())
    _, _, addr_text = final_recipient.partition(";")
    local_part, at_sign, domain_part = parseaddr(addr_text.strip())[1].partition("@")
    return DeliveryStatus(
        action=action.strip().lower(),
        code=code,
        output=diagnostic_code or status,
        final_recipient=f"{local_part.strip('"')}{at_sign}{domain_part}",
    )


def resolve_bounce_owner(rcpt_to: str) -> OutgoingMessage | None:
    """
    Return the outgoing message a bounce DSN reports about.

    The recipient MX returns the DSN to the VERP envelope recipient
    (`bounce+<token>@<sender-domain>`) relay minted when the message was
    submitted. Only relay can mint the token signature, so a message id
    alone names nothing. Anything else returns `None`.
    """
    value, _, signature = rcpt_to.partition("@")[0].partition("+")[2].rpartition(".")
    try:
        key = next(
            candidate
            for candidate in (None, *bounce_signer.fallback_keys)
            if hmac.compare_digest(
                bounce_signer.signature(value, key=candidate)[:20].encode(),
                signature.encode(),
            )
        )
        message_id = uuid.UUID(bytes=base64.urlsafe_b64decode(value + "=="))
        original = OutgoingMessage.objects.select_related("domain").get(pk=message_id)
        if rcpt_to.lower() != mint_bounce_address(original, key=key).lower():
            original = None
    except StopIteration, ValueError, ValidationError, OutgoingMessage.DoesNotExist:
        original = None
    return original


@task
def parse_bounce_report(message_pk):
    """
    Record a post-acceptance bounce DSN on the original outgoing message.

    Only messages in `sent` or `failed` status are recorded, since a
    DSN proves the recipient server accepted the message. A DSN only
    applies when its `Final-Recipient` matches the message recipient.
    A `failed` action bounces the message and suppresses the recipient,
    mirroring an inline 5xx rejection. A `delayed` action records a
    retry transmission for visibility without changing the message
    status. Any other action is not tracked.
    """
    message = IncomingMessage.objects.get(pk=message_pk)
    owner = resolve_bounce_owner(message.rcpt_to)
    delivery_status = None
    if owner is None:
        logger.warning("Bounce DSN %r matches no outgoing message", message_pk)
    else:
        try:
            delivery_status = parse_delivery_status(message.raw_body.read())
        except ValueError:
            logger.warning("Bounce DSN %r has no parseable delivery status", message_pk)
    if owner is not None and delivery_status is not None:
        with transaction.atomic():
            owner = (
                OutgoingMessage.objects.select_for_update()
                .select_related(
                    "org",
                    "domain",
                )
                .get(pk=owner.pk)
            )
            match delivery_status.action:
                case "failed" | "delayed" if owner.status not in (
                    OutgoingMessage.Status.SENT,
                    OutgoingMessage.Status.FAILED,
                ):
                    logger.warning(
                        "Bounce DSN %r does not apply to outgoing message %r in status %r",
                        message_pk,
                        owner.pk,
                        owner.status,
                    )
                case "failed" | "delayed" if (
                    delivery_status.final_recipient.lower() != owner.rcpt_to.lower()
                ):
                    logger.warning(
                        "Bounce DSN %r does not report recipient %r of outgoing message %r",
                        message_pk,
                        owner.rcpt_to,
                        owner.pk,
                    )
                case "delayed" if Transmission.objects.filter(
                    message=owner, status=Transmission.Status.RETRY
                ).exists():
                    logger.warning(
                        "Bounce DSN %r repeats a recorded retry for outgoing message %r",
                        message_pk,
                        owner.pk,
                    )
                case "failed":
                    Transmission.objects.create(
                        message=owner,
                        status=Transmission.Status.BOUNCED,
                        code=delivery_status.code,
                        output=delivery_status.output,
                    )
                    owner.status = OutgoingMessage.Status.BOUNCED
                    owner.save(update_fields=["status"])
                    SuppressionEntry.objects.create_or_update(
                        org=owner.org,
                        email=owner.rcpt_to,
                        reason=SuppressionEntry.Reason.BOUNCE,
                    )
                case "delayed":
                    Transmission.objects.create(
                        message=owner,
                        status=Transmission.Status.RETRY,
                        code=delivery_status.code,
                        output=delivery_status.output,
                    )
