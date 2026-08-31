"""SMTP handlers for outgoing mail submissions."""

import base64
import logging
import secrets
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction

from accounts.models import Organization
from domains.dkim import sign_message
from domains.models import Domain, canonicalize_domain_name
from services.email.proxy_protocol import ProxyProtocolMixin, get_client_ip

from .models import MsaCredential, OutgoingMessage, SuppressionEntry
from .tasks import check_outgoing_spam

logger = logging.getLogger(__name__)


def add_feedback_id(raw_bytes: bytes, org: Organization) -> tuple[bytes, str]:
    """Prepend a relay Feedback-ID header for FBL complaint attribution per org.

    relay's token replaces any customer-supplied Feedback-ID because the
    token is the attribution key for complaint reports. Return the
    message bytes and the minted Feedback-ID.
    """
    feedback_id = f"{org.pk}::{secrets.token_hex(12)}:relay"
    header = f"Feedback-ID: {feedback_id}\015\012".encode("ascii")
    return header + remove_feedback_id_headers(raw_bytes), feedback_id


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

    async def handle_DATA(self, server, session, envelope):
        """Store a submitted outgoing message."""
        credential = getattr(session, "credential", None)
        if credential is None:
            return "530 Authentication required"

        mail_from = envelope.mail_from or ""
        rcpt_to = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        raw_data = envelope.content
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        msg = message_from_bytes(raw_bytes)
        client_ip = get_client_ip(session)
        result = await process_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            msg,
            credential,
            getattr(session, "ssl", False),
            client_ip,
        )
        logger.info(f"Message from {mail_from} to {rcpt_to}: {result}")
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
            logger.info(
                f"Authenticated org '{credential.org}' with credential "
                f"'{credential.name or credential.key_prefix}…'"
            )
            return "235 Authentication successful"
        except ValueError, DatabaseError:
            logger.exception("AUTH error")
            return "535 Authentication failed"


class ImplicitTLSHandler(SMTPHandler):
    """Handler for implicit TLS (port 465) connections.

    aiosmtpd doesn't detect pre-wrapped TLS sockets, so `session.ssl`
    is never set for implicit TLS. Mark the session as encrypted before
    delegating to the standard handler so AUTH and TLS reporting work.
    """

    async def handle_DATA(self, server, session, envelope):
        session.ssl = True
        return await super().handle_DATA(server, session, envelope)


class BalancerHandler(SMTPHandler):
    """Handler for the plaintext balancer port behind the Caddy L4 proxy.

    Caddy terminates the client's TLS and forwards the session as plain
    SMTP with a PROXY protocol header. Mark the session as encrypted
    before delegating to the standard handler so AUTH and TLS reporting
    work.
    """

    async def handle_DATA(self, server, session, envelope):
        session.ssl = True
        return await super().handle_DATA(server, session, envelope)


@sync_to_async
def authenticate(username: str, key: str):
    """Authenticate an org by its slug and SMTP credential key. Return the
    credential, or `None` if authentication fails."""
    api_keys = MsaCredential.objects.select_related("org").filter(
        key_prefix=key[:8],
        org__slug=username,
        type__in=[MsaCredential.Type.SMTP, MsaCredential.Type.SMTP_IP],
        hold=False,
    )
    for api_key in api_keys:
        if api_key.verify_key(key):
            return api_key
    return None


def process_suppressed_message(
    mail_from, rcpt_to, raw_bytes, msg, credential, ssl, domain
):
    """Store a suppressed message without enqueuing delivery.

    Suppressed mail is never sent, so relay mints no Feedback-ID and FBL
    complaints can never be attributed to it. Strip customer-supplied
    Feedback-ID headers so only the Feedback-ID relay actually forwarded
    with ever persists.
    """
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")
    raw_bytes = remove_feedback_id_headers(raw_bytes)
    OutgoingMessage.objects.create(
        org=credential.org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        subject=subject,
        message_id=message_id,
        domain=domain,
        credential=credential,
        status=OutgoingMessage.Status.SUPPRESSED,
        received_with_tls=bool(ssl),
        headers=OutgoingMessage.headers_from_raw(raw_bytes),
        raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
    )
    logger.info(f"Suppressed message from {mail_from} to {rcpt_to}")
    return "250 OK"


@sync_to_async
def process_message(mail_from, rcpt_to, raw_bytes, msg, credential, ssl, client_ip):
    """Store a submitted outgoing message and enqueue its delivery unless
    the org is suspended."""
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")

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
        return process_suppressed_message(
            mail_from, rcpt_to, raw_bytes, msg, credential, ssl, domain
        )

    if (
        not credential.org.billing_is_active
        and not credential.org.members.filter(email__iexact=rcpt_to).exists()
    ):
        return "550 Recipient not allowed without active billing"

    if credential.org.suspended_at:
        return "550 Account suspended due to sender reputation"

    raw_bytes, feedback_id = add_feedback_id(raw_bytes, credential.org)
    raw_bytes = sign_message(raw_bytes, domain)

    message = OutgoingMessage.objects.create(
        org=credential.org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        subject=subject,
        message_id=message_id,
        domain=domain,
        credential=credential,
        feedback_id=feedback_id,
        received_with_tls=bool(ssl),
        status=OutgoingMessage.Status.PENDING,
        headers=OutgoingMessage.headers_from_raw(raw_bytes),
        raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
    )

    transaction.on_commit(
        lambda: check_outgoing_spam.enqueue(
            message_pk=str(message.id),
            client_ip=client_ip,
        )
    )

    return "250 OK"
