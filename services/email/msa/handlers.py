"""Store and submit outgoing mail."""

import base64
import logging
from email import message_from_bytes

from aiosmtpd.smtp import TLSSetupException
from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.utils import timezone

from abstract.email_utils import decode_header_value
from abstract.signals import request_scoped
from accounts.models import Organization
from domains.dkim import sign_message
from domains.models import Domain, canonicalize_domain_name
from services.email.message.models import Transmission
from services.email.proxy_protocol import ProxyProtocolMixin, get_client_ip

from .models import MsaCredential, OutgoingMessage, SuppressionEntry
from .tasks import check_outgoing_spam, deliver_message

logger = logging.getLogger(__name__)


def add_feedback_id(raw_bytes: bytes, org: Organization, domain: Domain) -> bytes:
    """
    Prepend the relay Feedback-ID header, replacing customer-supplied ones.

    The identifiers are the sending domain, the organization, and the mail
    type, followed by the SenderId that stays the same for every message.
    Providers aggregate FBL data per identifier, so a value that changes
    with each message would never be reported.
    """
    header = f"Feedback-ID: {domain.sender_domain}:{org.pk}:tx:relay\015\012"
    return header.encode("ascii") + remove_feedback_id_headers(raw_bytes)


def remove_feedback_id_headers(raw_bytes: bytes) -> bytes:
    """Return raw_bytes without customer-supplied Feedback-ID headers."""
    kept = []
    in_headers = True
    deleting = False
    for line in raw_bytes.splitlines(keepends=True):
        if in_headers and not line.strip(b"\r\n"):
            in_headers = False
            deleting = False
        if not in_headers:
            kept.append(line)
        elif deleting and line[:1] in b" \t":
            pass
        else:
            name = line.partition(b":")[0]
            deleting = name.lower().rstrip(b" \t") == b"feedback-id"
            if not deleting:
                kept.append(line)
    return b"".join(kept)


class SMTPHandler(ProxyProtocolMixin):
    """Receive authenticated outgoing mail submissions from SMTP clients."""

    async def handle_exception(self, error):
        session = getattr(self, "session", None)
        peer = getattr(session, "peer", None)
        if isinstance(error, TLSSetupException):
            logger.debug("%r TLS error during SMTP session", peer, exc_info=error)
            return f"500 Error: ({error.__class__.__name__}) {error}"
        logger.exception("%r SMTP session exception", peer)
        return f"500 Error: ({error.__class__.__name__}) {str(error)}"

    async def handle_DATA(self, server, session, envelope):
        """Store a submitted outgoing message."""
        credential = getattr(session, "credential", None)
        if credential is None:
            return "530 Authentication required"

        mail_from = envelope.mail_from or ""
        rcpt_to = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        raw_data = envelope.content
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        client_ip = get_client_ip(session)
        result = await process_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            credential,
            getattr(session, "ssl", False),
            client_ip,
            timezone.now(),
        )
        logger.info("Message from %r to %r: %r", mail_from, rcpt_to, result)
        return result

    async def handle_AUTH(self, server, session, envelope, arg):
        """Handle SMTP AUTH. Verify the username and API key."""
        try:
            match arg[0].upper():
                case "PLAIN":
                    decoded = base64.b64decode(arg[1]).decode("utf-8")
                    fields = decoded.split("\0")
                    if len(fields) < 3:
                        return "535 Authentication failed"
                    username, api_key = fields[1], fields[2]
                case _:
                    return "504 Unrecognized authentication type"

            credential = await authenticate(username, api_key)
            if credential is None:
                return "535 Authentication failed"
            session.credential = credential
        except ValueError, DatabaseError:
            logger.exception("AUTH error")
            return "535 Authentication failed"
        else:
            logger.info(
                "Authenticated org '%s' with credential '%s…'",
                credential.org,
                credential.name or credential.key_prefix,
            )
            return "235 Authentication successful"


class ImplicitTLSHandler(SMTPHandler):
    """
    Handler for implicit TLS (port 465) connections.

    aiosmtpd doesn't detect pre-wrapped TLS sockets, so `session.ssl`
    is never set for implicit TLS. Mark the session as encrypted before
    delegating to the standard handler so AUTH and TLS reporting work.
    """

    async def handle_DATA(self, server, session, envelope):
        session.ssl = True
        return await super().handle_DATA(server, session, envelope)


class BalancerHandler(ImplicitTLSHandler):
    """
    Handler for the plaintext balancer port behind the Caddy L4 proxy.

    Caddy terminates the client's TLS and forwards the session as plain
    SMTP with a PROXY protocol header. Marking the session as encrypted
    before delegating reflects Caddy's terminated TLS in TLS reporting.
    AUTH relies on this port being configured with auth_require_tls
    disabled, since the client-facing leg is TLS at the proxy.
    """


@sync_to_async
@request_scoped
def authenticate(username: str, key: str):
    """
    Authenticate an org by its slug and SMTP credential key.

    Return the credential, or `None` if authentication fails.
    """
    api_keys = MsaCredential.objects.select_related("org").filter(
        key_prefix=key[:4],
        org__slug=username,
        hold=False,
    )
    for api_key in api_keys:
        if api_key.verify_key(key):
            return api_key
    return None


def store_outgoing_message(
    *,
    org,
    rcpt_to,
    mail_from,
    domain,
    credential,
    status,
    ssl,
    client_ip,
    raw_bytes,
    started_at,
    is_system_mail=False,
    message_pk=None,
):
    """
    Store an outgoing message with its submission record.

    Enqueues spam processing for customer submissions, and delivery directly
    for the system mail relay authored itself.
    """
    parsed = message_from_bytes(raw_bytes)
    message_id = parsed.get("Message-ID", "")
    subject = decode_header_value(parsed.get("Subject", ""))
    # The message carries the marker, the credential can go away later.
    is_sandbox = (
        credential is not None and credential.type == MsaCredential.Type.SANDBOX
    )
    with Transmission.record_submission(ssl, started_at, client_ip) as transmission:
        transmission.message = message = OutgoingMessage.objects.create(
            id=message_pk,
            org=org,
            rcpt_to=rcpt_to,
            mail_from=mail_from,
            subject=subject,
            message_id=message_id,
            domain=domain,
            credential=credential,
            is_sandbox=is_sandbox,
            status=status,
            headers=OutgoingMessage.headers_from_raw(raw_bytes),
            raw_body=SimpleUploadedFile(
                "message.eml", raw_bytes, content_type="message/rfc822"
            ),
        )
    if status == OutgoingMessage.Status.PENDING:
        if is_system_mail:
            transaction.on_commit(
                lambda: deliver_message.enqueue(message_id=str(message.id))
            )
        else:
            transaction.on_commit(
                lambda: check_outgoing_spam.enqueue(
                    message_pk=str(message.id),
                    client_ip=client_ip,
                )
            )
    return message


def submit_relay_message(
    *,
    org,
    domain,
    email,
    mail_from,
    rcpt_to,
    started_at,
    message_pk=None,
    ssl=None,
    client_ip=None,
):
    """
    Stamp, sign and queue one message relay generated for an organization.

    The message leaves relay from the organization's own domain, which is
    what puts it in their dashboard and on their bill. A caller that passes
    message_pk renders the body against the ID the message will carry, so a
    message can link to its own transmission trace.
    """
    raw_bytes = add_feedback_id(email.message().as_bytes(), org, domain)
    raw_bytes = sign_message(raw_bytes, domain)
    return store_outgoing_message(
        org=org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        domain=domain,
        credential=None,
        status=OutgoingMessage.Status.PENDING,
        ssl=ssl,
        client_ip=client_ip,
        raw_bytes=raw_bytes,
        started_at=started_at,
        is_system_mail=True,
        message_pk=message_pk,
    )


@sync_to_async
@request_scoped
def process_message(
    mail_from, rcpt_to, raw_bytes, credential, ssl, client_ip, started_at
):
    """
    Store a submitted outgoing message and enqueue its delivery.

    A suppressed recipient is stored without delivery, even if the
    organization is suspended. Otherwise a suspended organization is refused
    before relay stores anything.
    A submission with a sandbox credential is stamped and signed like any
    other, and its delivery walk stops before the SMTP session.
    """
    if "@" not in mail_from:
        return "550 Sender domain not registered"

    try:
        from_domain = canonicalize_domain_name(mail_from.rsplit("@", 1)[1])
        domain = Domain.objects.get(name=from_domain, org=credential.org)
        resolved_domain = Domain.objects.root_for(
            from_domain,
            include_managed=True,
        )
    except Domain.DoesNotExist, ValidationError:
        return "550 Sender domain not registered"

    if (
        resolved_domain.pk != domain.pk
        or resolved_domain.org_id != domain.org_id
        or resolved_domain.name != domain.name
    ):
        return "550 Sender domain not registered"

    if SuppressionEntry.objects.is_suppressed(credential.org, rcpt_to):
        # Suppressed mail never leaves relay, so relay mints no Feedback-ID
        # and the stored copy carries none.
        raw_bytes = remove_feedback_id_headers(raw_bytes)
        message = store_outgoing_message(
            org=credential.org,
            rcpt_to=rcpt_to,
            mail_from=mail_from,
            domain=domain,
            credential=credential,
            status=OutgoingMessage.Status.SUPPRESSED,
            ssl=ssl,
            client_ip=client_ip,
            raw_bytes=raw_bytes,
            started_at=started_at,
        )
        logger.info("Suppressed message %r", message)
        return "250 OK"

    if (
        not credential.org.billing_is_active
        and not credential.org.members.filter(email__iexact=rcpt_to).exists()
    ):
        return "550 Recipient not allowed without active billing"

    if credential.org.suspended_at:
        return "550 Account suspended due to sender reputation"

    raw_bytes = add_feedback_id(raw_bytes, credential.org, domain)
    raw_bytes = sign_message(raw_bytes, domain)
    store_outgoing_message(
        org=credential.org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        domain=domain,
        credential=credential,
        status=OutgoingMessage.Status.PENDING,
        ssl=ssl,
        client_ip=client_ip,
        raw_bytes=raw_bytes,
        started_at=started_at,
    )
    return "250 OK"
