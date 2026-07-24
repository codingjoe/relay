"""MX handler for incoming mail delivery.

Accepts unauthenticated mail from remote MTAs for domains that match
an organization's root domain. Stores the raw body and enqueues webhook
dispatch.
"""

import logging
from email import message_from_bytes

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.db import transaction

from domains.models import Domain

from .models import IncomingMessage
from .tasks import dispatch_webhook

logger = logging.getLogger(__name__)


class MXHandler:
    """Receive incoming mail from remote SMTP servers via MX delivery."""

    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        mail_from = envelope.mail_from or ""
        rcpt_to = envelope.rcpt_tos[0] if envelope.rcpt_tos else ""
        raw_data = envelope.content
        raw_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
        result = await process_incoming_message(
            mail_from,
            rcpt_to,
            raw_bytes,
            getattr(session, "tls", False),
        )
        logger.info(f"Incoming message from {mail_from} to {rcpt_to}: {result}")
        return result


@sync_to_async
def process_incoming_message(mail_from, rcpt_to, raw_bytes, tls):
    """Validate the recipient domain and store the incoming message."""
    msg = message_from_bytes(raw_bytes)
    rcpt_domain = rcpt_to.split("@")[-1] if "@" in rcpt_to else ""

    # Find a root domain that the recipient domain is a subdomain of (or equal to)
    domain = find_root_domain(rcpt_domain)
    if domain is None:
        return "550 Relay not authorised for this recipient"

    message = IncomingMessage(
        org=domain.org,
        receiving_domain=rcpt_domain,
        mail_from=mail_from,
        rcpt_to=rcpt_to,
        subject=msg.get("Subject", ""),
        message_id=msg.get("Message-ID", ""),
        received_with_tls=bool(tls),
        status=IncomingMessage.Status.RECEIVED,
    )
    try:
        message.raw_body.save(f"{message.id}.eml", ContentFile(raw_bytes), save=False)
        message.save()
    except Exception as e:
        logger.error(f"Failed to store incoming message body: {e}")
        return "451 Requested action aborted: local error"

    transaction.on_commit(lambda: dispatch_webhook.enqueue(message_id=str(message.id)))

    return "250 OK"


def find_root_domain(rcpt_domain):
    """Find the root Domain that owns rcpt_domain (exact match or parent suffix)."""
    if not rcpt_domain:
        return None
    rcpt_lower = rcpt_domain.lower()
    # Try exact match first, then progressively strip subdomain labels
    parts = rcpt_lower.split(".")
    for i in range(len(parts)):
        candidate = ".".join(parts[i:])
        domain = (
            Domain.objects.filter(name__iexact=candidate, org__isnull=False)
            .select_related("org")
            .first()
        )
        if domain:
            return domain
    return None
