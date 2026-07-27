import time

import pytest

from mx.tasks import WEBHOOK_RETRY_DELAYS, WebhookEvent, WebhookJSONEncoder


class TestWebhookEventFromTest:
    def test_from_test_event__returns_test_payload(self):
        event = WebhookEvent.from_message(None, is_test=True)
        assert event.type == "email.test"
        assert event.message_id == ""
        assert event.sender == ""
        assert event.recipient == ""
        assert event.subject == ""
        assert event.rfc822_message_id == ""
        assert event.received_with_tls is False
        assert event.receiving_domain == ""
        assert event.body_url is None

    def test_from_test_event__sets_received_at(self):
        before = int(time.time())
        event = WebhookEvent.from_message(None, is_test=True)
        after = int(time.time())
        ts = time.mktime(time.strptime(event.received_at, "%Y-%m-%dT%H:%M:%SZ"))
        assert before <= ts <= after


@pytest.mark.django_db
class TestWebhookEventFromMessage:
    def test_from_message__populates_all_fields(self, org):
        from django.core.files.base import ContentFile

        from mx.models import IncomingMessage

        msg = IncomingMessage(
            org=org,
            receiving_domain="example.com",
            mail_from="alice@example.com",
            rcpt_to="bob@example.com",
            subject="Hello",
            message_id="<abc@example.com>",
            received_with_tls=True,
        )
        msg.raw_body.save("test.eml", ContentFile(b"raw bytes"), save=False)
        msg.save()

        event = WebhookEvent.from_message(msg)
        assert event.type == "email.received"
        assert event.message_id == str(msg.id)
        assert event.sender == "alice@example.com"
        assert event.recipient == "bob@example.com"
        assert event.subject == "Hello"
        assert event.rfc822_message_id == "<abc@example.com>"
        assert event.received_with_tls is True
        assert event.receiving_domain == "example.com"
        assert event.body_url is not None
        assert event.body_url.endswith(".eml")

    def test_from_message__body_url_is_none_when_no_raw_body(self, org):
        from mx.models import IncomingMessage

        msg = IncomingMessage.objects.create(
            org=org,
            receiving_domain="example.com",
            mail_from="alice@example.com",
            rcpt_to="bob@example.com",
            subject="Hello",
            message_id="<abc@example.com>",
        )
        event = WebhookEvent.from_message(msg)
        assert event.body_url is None


class TestWebhookJSONEncoder:
    def test_default__serialises_webhook_event(self):
        event = WebhookEvent(
            type="email.received",
            message_id="abc",
            sender="a@b",
            recipient="c@d",
            subject="s",
            rfc822_message_id="<x>",
            received_with_tls=True,
            receiving_domain="d",
            body_url=None,
            received_at="2026-01-01T00:00:00Z",
        )
        import json

        encoded = json.dumps({"event": event}, cls=WebhookJSONEncoder)
        assert "email.received" in encoded
        assert "abc" in encoded


class TestRetrySchedule:
    def test_retry_delays__starts_immediately(self):
        assert WEBHOOK_RETRY_DELAYS[0] == 0

    def test_retry_delays__monotonically_increasing(self):
        for earlier, later in zip(WEBHOOK_RETRY_DELAYS, WEBHOOK_RETRY_DELAYS[1:]):
            assert later > earlier

    def test_retry_delays__ends_after_24h(self):
        assert WEBHOOK_RETRY_DELAYS[-1] == 24 * 60 * 60
