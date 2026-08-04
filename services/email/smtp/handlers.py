"""SMTP handlers for outgoing mail submissions."""

import base64
import logging
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import DatabaseError, transaction

from domains.models import Domain

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
    return credential.org.memberships.filter(user__username=username).first()


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


@sync_to_async
def process_message(mail_from, rcpt_to, raw_bytes, msg, credential, sender, ssl):
    """Store a submitted outgoing message and enqueue its delivery."""
    subject = msg.get("Subject", "")
    message_id = msg.get("Message-ID", "")

    from_domain = mail_from.split("@")[-1] if "@" in mail_from else ""
    free_domain = settings.RELAY_FREE_SENDER_DOMAIN.lower()

    if (
        from_domain.lower() == free_domain
        and rcpt_to.lower() != (sender.email or "").lower()
    ):
        return "550 Recipient not allowed for free sender domain"

    if SuppressionEntry.objects.is_suppressed(credential.org, rcpt_to):
        return "550 Recipient suppressed"

    domain = (
        Domain.objects.filter(name__iexact=from_domain).first() if from_domain else None
    )

    message = OutgoingMessage(
        sender=sender,
        org=credential.org,
        rcpt_to=rcpt_to,
        mail_from=mail_from,
        subject=subject,
        message_id=message_id,
        domain=domain,
        credential=credential,
        status=OutgoingMessage.Status.PENDING,
        received_with_tls=bool(ssl),
    )
    try:
        message.raw_body.save(f"{message.id}.eml", ContentFile(raw_bytes), save=False)
        message.save()
    except Exception as e:  # noqa: BLE001 — storage backend raises varied exceptions
        logger.error(f"Failed to store message body: {e}")
        return "451 Requested action aborted: local error"

    transaction.on_commit(
        lambda: deliver_message.enqueue(
            message_id=str(message.id),
            rcpt_to=rcpt_to,
            mail_from=mail_from,
            domain_id=domain.pk if domain else None,
        )
    )

    return "250 OK"
