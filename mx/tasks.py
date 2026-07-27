"""Webhook dispatch tasks for incoming mail."""

import json
import logging
import secrets
import time
import uuid
from dataclasses import dataclass, field

import httpx
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.tasks import task
from django.utils import timezone

from .models import IncomingMessage, Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


# Standard Webhooks retry schedule: time since *original* delivery attempt.
# Each entry is the delay (in seconds) before the next attempt.
WEBHOOK_RETRY_DELAYS: tuple[int, ...] = (
    0,  # immediate (first attempt)
    5,  # 5 seconds
    5 * 60,  # 5 minutes
    30 * 60,  # 30 minutes
    2 * 60 * 60,  # 2 hours
    5 * 60 * 60,  # 5 hours
    10 * 60 * 60,  # 10 hours
    14 * 60 * 60,  # 14 hours
    20 * 60 * 60,  # 20 hours
    24 * 60 * 60,  # 24 hours
)


@task
def dispatch_webhook(message_id, attempt=0):
    """Deliver an incoming message to all matching active webhooks for its org.

    Retries are scheduled by re-enqueueing the same task with an incremented
    ``attempt`` index, per the Standard Webhooks retry schedule. ``message``
    status is only updated on the final attempt.
    """
    message = IncomingMessage.objects.get(pk=message_id)
    webhooks = Webhook.objects.filter(org=message.org, is_active=True)
    is_final_attempt = attempt >= len(WEBHOOK_RETRY_DELAYS) - 1
    deliveries = [
        deliver_with_retries(message, webhook, attempt, is_final_attempt)
        for webhook in webhooks
        if webhook.matches(message.rcpt_to)
    ]
    any_sent = any(deliveries)
    any_failed = any(not d for d in deliveries)

    match is_final_attempt, [any_sent, any_failed]:
        case False, _:
            pass
        case _, [True, _]:
            message.status = IncomingMessage.Status.WEBHOOK_SENT
            message.save(update_fields=["status"])
        case _, [False, True]:
            message.status = IncomingMessage.Status.WEBHOOK_FAILED
            message.save(update_fields=["status"])
        case _:
            message.status = IncomingMessage.Status.DROPPED
            message.save(update_fields=["status"])


def schedule_retry(message_id, webhook, attempt):
    match attempt < len(WEBHOOK_RETRY_DELAYS) - 1:
        case True:
            delay = WEBHOOK_RETRY_DELAYS[attempt + 1] + secrets.randbelow(30)
            dispatch_webhook.using(run_after=time.time() + delay).enqueue(
                message_id=message_id, attempt=attempt + 1
            )
        case False:
            pass


def deliver_with_retries(message, webhook, attempt, is_final_attempt):
    ok, status_code = deliver_to_webhook(message, webhook)
    match ok, status_code:
        case (True, _):
            webhook.last_used_at = timezone.now()
            webhook.save(update_fields=["last_used_at"])
        case (False, 410):
            webhook.is_active = False
            webhook.save(update_fields=["is_active"])
        case (False, _) if not is_final_attempt:
            schedule_retry(str(message.id), webhook, attempt)
    return ok


@dataclass
class WebhookEvent:
    """A flat webhook event payload, sans the raw message body."""

    type: str
    message_id: str
    sender: str
    recipient: str
    subject: str
    rfc822_message_id: str
    received_with_tls: bool
    receiving_domain: str
    body_url: str | None
    received_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )

    @classmethod
    def from_message(cls, message, *, is_test=False):
        """Build a webhook event payload from a stored message (or a test ping)."""
        if is_test and message is None:
            return cls(
                type="email.test",
                message_id="",
                sender="",
                recipient="",
                subject="",
                rfc822_message_id="",
                received_with_tls=False,
                receiving_domain="",
                body_url=None,
            )
        return cls(
            type="email.test" if is_test else "email.received",
            message_id=str(message.id),
            sender=message.mail_from,
            recipient=message.rcpt_to,
            subject=message.subject,
            rfc822_message_id=message.message_id,
            received_with_tls=message.received_with_tls,
            receiving_domain=message.receiving_domain,
            body_url=message.raw_body.url if message.raw_body else None,
        )


class WebhookJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if isinstance(obj, WebhookEvent):
            return obj.__dict__
        return super().default(obj)


def deliver_to_webhook(message, webhook, is_test=False):
    msg_id = f"msg_{uuid.uuid7()}"
    timestamp = int(time.time())
    payload = WebhookEvent.from_message(message, is_test=is_test)
    payload_bytes = json.dumps(payload, sort_keys=True, cls=WebhookJSONEncoder).encode()
    signature = webhook.sign(msg_id, timestamp, payload_bytes)

    try:
        response = httpx.post(
            webhook.url,
            content=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "webhook-id": msg_id,
                "webhook-timestamp": str(timestamp),
                "webhook-signature": signature,
            },
            timeout=settings.RELAY_WEBHOOK_TIMEOUT,
        )
        ok = response.is_success
        status_code = response.status_code
        WebhookDelivery.objects.create(
            message=message,
            webhook=webhook,
            is_test=is_test,
            status=WebhookDelivery.Status.SENT if ok else WebhookDelivery.Status.FAILED,
            response_code=status_code,
            response_body=response.text[:2000],
        )
    except httpx.HTTPError as e:
        logger.error(f"Webhook delivery to {webhook.url} failed: {e}")
        WebhookDelivery.objects.create(
            message=message,
            webhook=webhook,
            is_test=is_test,
            status=WebhookDelivery.Status.FAILED,
            response_body=str(e)[:2000],
        )
        return False, 0

    return ok, status_code
