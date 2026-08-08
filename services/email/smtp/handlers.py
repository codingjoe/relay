"""SMTP handlers for outgoing mail submissions."""

import base64
import logging
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction

from domains.models import Domain, canonicalize_domain_name

from .models import OutgoingMessage, SmtpCredential, SuppressionEntry
from .tasks import deliver_message

logger = logging.getLogger(__name__)


class SMTPHandler:
    """Receive authenticated outgoing mail submissions from SMTP clients."""

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        """Store a submitted outgoing message."""
        credential = getattr(session, "credential", None)
        sender = getattr(session, "sender", None)
        if credential is None or sender is None:
            return "530 Authentication required"

        mail_from = envelope.mail_from or ""
        rcpt_to = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        raw_data = envelope.content
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        msg = message_from_bytes(raw_bytes)
        result = await process_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            msg,
            credential,
            sender,
            getattr(session, "ssl", False),
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
            membership = await get_membership(credential, username)
            session.sender = membership.user
            return "235 Authentication successful"
        except (ValueError, DatabaseError) as e:
            logger.error(f"AUTH error: {e}")
            return "535 Authentication failed"


@sync_to_async
def get_membership(credential, username):
    """Return the membership linking the credential's org to the given user."""
    return credential.org.memberships.get(user__username=username)


@sync_to_async
def authenticate(username: str, key: str):
    """Authenticate a user by their SMTP credential. Return the credential,
    or `None` if authentication fails."""
    api_keys = SmtpCredential.objects.select_related("org").filter(
        key_prefix=key[:8],
        org__memberships__user__username=username,
        type__in=[SmtpCredential.Type.SMTP, SmtpCredential.Type.SMTP_IP],
        hold=False,
    )
    for api_key in api_keys:
        if api_key.verify_key(key):
            return api_key
    return None


def process_suppressed_message(
    mail_from, rcpt_to, raw_bytes, msg, credential, sender, ssl, domain
):
    """Store a suppressed message without enqueuing delivery."""
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")
    OutgoingMessage.objects.create(
        sender=sender,
        org=credential.org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        subject=subject,
        message_id=message_id,
        domain=domain,
        credential=credential,
        status=OutgoingMessage.Status.SUPPRESSED,
        received_with_tls=bool(ssl),
        raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
    )
    logger.info(f"Suppressed message from {mail_from} to {rcpt_to}")
    return "250 OK"


@sync_to_async
def process_message(mail_from, rcpt_to, raw_bytes, msg, credential, sender, ssl):
    """Store a submitted outgoing message and enqueue its delivery."""
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")

    if "@" not in mail_from:
        return "550 Sender domain not registered"

    try:
        from_domain = canonicalize_domain_name(mail_from.rsplit("@", 1)[1])
        domain = Domain.objects.get(name=from_domain, org=credential.org)
        resolved_domain = Domain.objects.root_for(from_domain)
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
            mail_from, rcpt_to, raw_bytes, msg, credential, sender, ssl, domain
        )

    if (
        not credential.org.billing_is_active
        and not credential.org.members.filter(email__iexact=rcpt_to).exists()
    ):
        return "550 Recipient not allowed without active billing"

    message = OutgoingMessage.objects.create(
        sender=sender,
        org=credential.org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        subject=subject,
        message_id=message_id,
        domain=domain,
        credential=credential,
        received_with_tls=bool(ssl),
        raw_body=SimpleUploadedFile(f"{message_id or 'message'}.eml", raw_bytes),
    )

    transaction.on_commit(
        lambda: deliver_message.enqueue(
            message_id=str(message.id),
        )
    )

    return "250 OK"
