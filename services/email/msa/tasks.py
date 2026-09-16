import logging
import random

import aiosmtplib
import dns.resolver
from asgiref.sync import async_to_sync, sync_to_async
from django.conf import settings
from django.tasks import task
from django.utils import timezone

from abstract.timing import measure
from services.email.mta_sts import MtaStsPolicy
from services.email.spam.client import SpamAction, check_message
from services.email.spam.retry import SPAM_SCAN_RETRY
from services.email.tls import parse_peer_certificates

logger = logging.getLogger(__name__)


class MxLookupError(Exception):
    """The MX lookup for a recipient domain failed."""

    def __init__(self, domain, reason):
        super().__init__(f"MX lookup for {domain} failed: {reason}")


class AmbiguousSenderDomainError(ValueError):
    """The sender domain does not resolve to a single root domain."""

    def __init__(self):
        super().__init__("Outgoing message sender domain is ambiguous")


class SenderDomainMismatchError(ValueError):
    """The sender domain does not match the resolved root domain."""

    def __init__(self):
        super().__init__("Outgoing message sender domain does not match")


@task(queue_name="delivery")
def deliver_message(message_id):
    """
    Deliver a queued outgoing message to its recipients.

    Drop the message instead when the org is suspended.
    """
    from services.email.message.models import Transmission

    from .models import OutgoingMessage

    message = OutgoingMessage.objects.select_related("domain", "org").get(pk=message_id)
    if message.org.suspended_at:
        message.status = OutgoingMessage.Status.DROPPED
        message.save(update_fields=["status", "modified_at"])
        dropped_at = timezone.now()
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            code=550,
            output="550 Account suspended due to sender reputation",
            started_at=dropped_at,
            finished_at=dropped_at,
        )
        return

    try:
        with measure() as interval:
            send_outgoing_message(message)
    except Exception as e:  # storage backend raises varied exceptions
        logger.exception("Transmission error for message %r", message_id)
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            details=str(e),
            started_at=interval.started_at,
            finished_at=interval.finished_at,
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
    from .models import OutgoingMessage

    resolve_sender_domain(message)
    raw_bytes = message.raw_body.read()
    return_path = (
        f"{settings.RELAY_BOUNCE_LOCAL_PART}+{message.id}"
        f"@{message.domain.sender_domain}"
    )
    rcpt_domain = message.rcpt_to.split("@")[-1]
    with measure() as interval:
        try:
            mx_hosts = fetch_mx_hosts(rcpt_domain)
        except MxLookupError as error:
            mx_hosts = []
            no_hosts_reason = str(error)
        else:
            no_hosts_reason = (
                "" if mx_hosts else f"No MX records found for {rcpt_domain}"
            )

    if no_hosts_reason:
        record_failed_attempt(message, interval, details=no_hosts_reason)
        status, failure = OutgoingMessage.Status.FAILED, no_hosts_reason
    else:
        status, failure = deliver_via_mx_hosts(
            message, mx_hosts, raw_bytes, return_path
        )
    if failure:
        logger.error(
            "Message %s to %s could not be delivered: %s",
            message.id,
            message.rcpt_to,
            failure,
        )
    message.status = status
    message.save(update_fields=["status"])


def deliver_via_mx_hosts(message, mx_hosts, raw_bytes, return_path):
    """
    Try every MX host in preference order and record one transmission per attempt.

    Return the status the message ends in and, when no host accepted it, the
    reasons every host refused.
    """
    from services.email.message.models import Transmission

    from .models import OutgoingMessage

    rcpt_domain = message.rcpt_to.split("@")[-1]
    reasons = []
    for mx_host in mx_hosts:
        with measure() as interval:
            allowed, reason = MtaStsPolicy.get(rcpt_domain).allows(mx_host)
        if not allowed:
            logger.warning(
                "MTA-STS blocked message %s to %s via %r: %s",
                message.id,
                message.rcpt_to,
                mx_host,
                reason,
            )
            reasons.append((mx_host, reason))
            record_failed_attempt(
                message, interval, details=reason, remote_host=mx_host
            )
            continue
        try:
            with measure() as interval:
                response, tls_details = async_to_sync(send_via_mx)(
                    raw_bytes,
                    mx_host,
                    return_path,
                    [message.rcpt_to],
                )
        except (
            aiosmtplib.SMTPResponseException,
            aiosmtplib.SMTPRecipientsRefused,
        ) as error:
            code, output = format_smtp_refusal(error)
            match code // 100:
                case 5:
                    # A permanent rejection suppresses the recipient address.
                    record_bounce(message, interval, code, output, mx_host)
                    logger.warning(
                        "Message %s to %s bounced at %r: %r",
                        message.id,
                        message.rcpt_to,
                        mx_host,
                        output,
                    )
                    return OutgoingMessage.Status.BOUNCED, ""
                case _:
                    reasons.append((mx_host, output))
                    record_failed_attempt(
                        message,
                        interval,
                        details=refusal_details(code),
                        remote_host=mx_host,
                        code=code,
                        output=output,
                    )
        except (aiosmtplib.SMTPException, OSError) as error:
            details = f"{type(error).__name__}: {error}"
            reasons.append((mx_host, details))
            record_failed_attempt(
                message,
                interval,
                details=details,
                remote_host=mx_host,
            )
        else:
            Transmission.objects.create(
                message=message,
                status=Transmission.Status.SENT,
                output=str(response),
                remote_host=mx_host,
                **tls_details,
            )
            logger.info(
                "Message %s to %s delivered via %r: %r",
                message.id,
                message.rcpt_to,
                mx_host,
                response,
            )
            return OutgoingMessage.Status.SENT, ""
    return (
        OutgoingMessage.Status.FAILED,
        "; ".join(f"{host}: {reason}" for host, reason in reasons),
    )


def refusal_details(code):
    """Describe a refusal that did not accept the message."""
    match code // 100:
        case 4:
            return "Temporary failure, the remote server asked relay to try again later"
        case _:
            return "The remote server did not accept the message"


def format_smtp_refusal(error):
    """
    Return the status code and the answer line of a refused SMTP command.

    A refused recipient arrives as `SMTPRecipientsRefused`, which carries
    the code and the answer per recipient instead of on the exception.
    """
    match error:
        case aiosmtplib.SMTPRecipientsRefused(recipients=[refusal, *_]):
            code, answer = refusal.code, refusal.message
        case aiosmtplib.SMTPResponseException():
            code, answer = error.code, error.message
        case _:
            code, answer = 0, str(error)
    if isinstance(answer, bytes):
        answer = answer.decode(errors="replace")
    return code, f"{code} {answer}"


def record_failed_attempt(
    message, interval, details, remote_host="", code=None, output=""
):
    """Record one failed delivery attempt over its measured interval."""
    from services.email.message.models import Transmission

    Transmission.objects.create(
        message=message,
        status=Transmission.Status.FAILED,
        details=details,
        remote_host=remote_host,
        code=code,
        output=output,
        started_at=interval.started_at,
        finished_at=interval.finished_at,
    )


def record_bounce(message, interval, code, output, remote_host):
    """Record a permanent bounce and suppress the recipient address."""
    from services.email.message.models import Transmission

    from .models import SuppressionEntry

    Transmission.objects.create(
        message=message,
        status=Transmission.Status.BOUNCED,
        details="Permanent rejection, relay suppressed the recipient address",
        code=code,
        output=output,
        remote_host=remote_host,
        started_at=interval.started_at,
        finished_at=interval.finished_at,
    )
    SuppressionEntry.objects.create_or_update(
        org=message.org,
        email=message.rcpt_to,
        reason=SuppressionEntry.Reason.BOUNCE,
    )


def fetch_mx_hosts(domain):
    """
    Return the recipient domain's MX hosts, ordered by preference.

    Raise `MxLookupError` when the lookup itself fails, so a resolver
    problem is never reported as a missing MX record.
    """
    try:
        records = dns.resolver.resolve(domain, "MX")
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer:
        return []
    except dns.exception.DNSException as error:
        raise MxLookupError(domain, error) from error
    return [
        str(record.exchange).rstrip(".")
        for record in sorted(records, key=lambda record: record.preference)
    ]


async def send_via_mx(
    raw_bytes: bytes, mx_host: str, sender: str, recipients: list[str]
) -> tuple[str, dict]:
    """
    Deliver a message to an MX host over STARTTLS on port 25.

    Returns the SMTP response with the negotiated TLS details.
    """
    from kms.models import Certificate
    from services.email.message.models import Transmission

    with measure() as interval:
        async with aiosmtplib.SMTP(
            hostname=mx_host,
            port=25,
            use_tls=False,
            start_tls=True,
            local_hostname=settings.RELAY_SMTP_PUBLIC_HOSTNAME,
            source_address=(
                (random.choice(settings.RELAY_SMTP_SOURCE_IPS), 0)
                if settings.RELAY_SMTP_SOURCE_IPS
                else None
            ),
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
        "local_ip_address": sockname[0] if sockname else None,
        "remote_ip_address": peername[0] if peername else None,
        "started_at": interval.started_at,
        "finished_at": interval.finished_at,
    }
    if ssl_object is not None:
        tls_details["tls_certificate"] = await sync_to_async(
            Certificate.store_presented_chain
        )(parse_peer_certificates(ssl_object))
    return response, tls_details


@task(queue_name="egress", retry=SPAM_SCAN_RETRY)
def check_outgoing_spam(message_pk, client_ip):
    """
    Check an outgoing message for spam before delivery.

    Messages for suspended orgs are dropped without a spam check. Clean
    messages are enqueued for delivery.

    """
    from services.email.message.models import SpamCheck

    from .models import OutgoingMessage

    message = OutgoingMessage.objects.select_related("org").get(pk=message_pk)
    if message.org.suspended_at:
        from services.email.message.models import Transmission

        message.status = OutgoingMessage.Status.DROPPED
        message.save(update_fields=["status", "modified_at"])
        dropped_at = timezone.now()
        Transmission.objects.create(
            message=message,
            status=Transmission.Status.FAILED,
            code=550,
            output="550 Account suspended due to sender reputation",
            started_at=dropped_at,
            finished_at=dropped_at,
        )
        return

    raw_bytes = message.raw_body.read()
    with SpamCheck(message=message) as timer:
        spam = async_to_sync(check_message)(raw_bytes, client_ip=client_ip)
        timer.score = spam.score
        timer.scan_ms = spam.scan_ms
        timer.antivirus_ms = spam.antivirus_ms
        timer.profile_ms = spam.profile_ms
    is_spam = (
        spam.action == SpamAction.REJECT
        or spam.score >= settings.RELAY_RSPAMD_HOLD_SCORE
    )
    message.spam_score = spam.score
    message.spam_action = spam.action
    message.virus_action = spam.virus_action
    message.virus_name = spam.virus_name
    message.virus_symbols = spam.virus_symbols
    if is_spam:
        message.status = OutgoingMessage.Status.HELD
    message.save(
        update_fields=[
            "spam_score",
            "spam_action",
            "virus_action",
            "virus_name",
            "virus_symbols",
            "status",
        ]
    )
    if not is_spam:
        deliver_message.enqueue(message_id=str(message.pk))
