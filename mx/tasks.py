"""Webhook dispatch tasks for incoming mail and TLS-RPT report parsing.

Retry schedule and delivery semantics follow the Standard Webhooks spec:
https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md#deliverability-and-reliability
"""

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

from .models import IncomingMessage, TlsFailure, TlsReport, Webhook, WebhookDelivery
from .parser import extract_attachment, parse_tls_json

logger = logging.getLogger(__name__)


# Standard Webhooks retry schedule — delay *between* consecutive attempts,
# with jitter added at enqueue time. See "Deliverability and reliability":
# https://github.com/standard-webhooks/standard-webhooks/blob/main/spec/standard-webhooks.md#deliverability-and-reliability
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
def dispatch_webhook(message_id):
    """Fan out an incoming message to all matching active webhooks."""
    message = IncomingMessage.objects.get(pk=message_id)
    webhooks = [
        webhook
        for webhook in Webhook.objects.filter(org=message.org, is_active=True)
        if webhook.matches(message.rcpt_to)
    ]
    match webhooks:
        case []:
            message.status = IncomingMessage.Status.DROPPED
            message.save(update_fields=["status"])
        case _:
            for webhook in webhooks:
                deliver_webhook.enqueue(
                    message_id=message_id, webhook_id=str(webhook.pk)
                )


@task
def deliver_webhook(message_id, webhook_id, attempt=0):
    """Deliver to a single webhook, retrying per the Standard Webhooks schedule."""
    message = IncomingMessage.objects.get(pk=message_id)
    webhook = Webhook.objects.get(pk=webhook_id)
    if not webhook.is_active:
        mark_failed_if_pending(message)
        return

    ok, status_code = deliver_to_webhook(message, webhook)
    match ok, status_code:
        case (True, _):
            Webhook.objects.filter(pk=webhook.pk).update(last_used_at=timezone.now())
            message.status = IncomingMessage.Status.WEBHOOK_SENT
            message.save(update_fields=["status"])
        case (False, 410):
            Webhook.objects.filter(pk=webhook.pk).update(is_active=False)
            mark_failed_if_pending(message)
        case (False, _) if attempt < len(WEBHOOK_RETRY_DELAYS) - 1:
            delay = WEBHOOK_RETRY_DELAYS[attempt + 1] + secrets.randbelow(30)
            deliver_webhook.using(run_after=time.time() + delay).enqueue(
                message_id=message_id, webhook_id=webhook_id, attempt=attempt + 1
            )
        case _:
            mark_failed_if_pending(message)


def mark_failed_if_pending(message):
    """Set `WEBHOOK_FAILED` only if the message has not yet been delivered."""
    IncomingMessage.objects.filter(
        pk=message.id, status=IncomingMessage.Status.RECEIVED
    ).update(status=IncomingMessage.Status.WEBHOOK_FAILED)


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


@task
def parse_tls_report(report_pk):
    """Parse a received TLS-RPT report and store its failures."""
    report = TlsReport.objects.select_related("incoming_message").get(pk=report_pk)
    try:
        raw_bytes = report.incoming_message.raw_body.read()
        data = extract_attachment(raw_bytes)
        if data is None:
            raise ValueError("No attachment found in TLS-RPT report email.")
        parsed = parse_tls_json(data)
        meta = parsed["metadata"]

        # Check for a duplicate (already-parsed report with same domain + report_id).
        if (
            meta["report_id"]
            and TlsReport.objects.filter(
                domain=report.domain, report_id=meta["report_id"]
            )
            .exclude(pk=report.pk)
            .exists()
        ):
            logger.info(f"Duplicate TLS-RPT report {report_pk}, discarding.")
            report.delete()
            return

        report.reporting_org = meta["reporting_org"]
        report.reporting_email = meta["reporting_email"]
        report.report_id = meta["report_id"]
        report.begin_at = meta["begin_at"]
        report.end_at = meta["end_at"]

        failures = []
        total_successful = 0
        total_failed = 0
        for policy in parsed["policies"]:
            total_successful += policy["successful_session_count"]
            total_failed += policy["failed_session_count"]
            for failure_data in policy["failures"]:
                failure_data["policy_type"] = policy["policy_type"]
                failure_data["policy_domain"] = policy["policy_domain"]
                failures.append(TlsFailure(report=report, **failure_data))

        report.successful_session_count = total_successful
        report.failed_session_count = total_failed

        TlsFailure.objects.bulk_create(failures)
        report.status = TlsReport.Status.PARSED
        report.error = ""
    except Exception as e:  # noqa: BLE001
        logger.error(f"Failed to parse TLS-RPT report {report_pk}: {e}")
        report.status = TlsReport.Status.FAILED
        report.error = str(e)
    finally:
        if report.pk:
            report.save(
                update_fields=[
                    "reporting_org",
                    "reporting_email",
                    "report_id",
                    "begin_at",
                    "end_at",
                    "successful_session_count",
                    "failed_session_count",
                    "status",
                    "error",
                ]
            )
