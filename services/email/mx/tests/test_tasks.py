import itertools
import time

import pytest
from django.test import override_settings

from services.email.mx.tasks import (
    WEBHOOK_RETRY_DELAYS,
    WebhookEvent,
    WebhookJSONEncoder,
)


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

        from services.email.mx.models import IncomingMessage

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
        from services.email.mx.models import IncomingMessage

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
        for earlier, later in itertools.pairwise(WEBHOOK_RETRY_DELAYS):
            assert later > earlier

    def test_retry_delays__ends_after_24h(self):
        assert WEBHOOK_RETRY_DELAYS[-1] == 24 * 60 * 60


LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


class TestNotifyPostmasterRecipients:
    @pytest.mark.django_db(transaction=True)
    def test_notify__sends_to_all_members_with_email(self, org, user, other_user):
        from django.core import mail

        from accounts.models import Membership
        from services.email.mx.models import IncomingMessage
        from services.email.mx.tasks import notify_postmaster_recipients

        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        msg = IncomingMessage.objects.create(
            org=org,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        with override_settings(EMAIL_BACKEND=LOCMEM):
            notify_postmaster_recipients.func(message_pk=str(msg.id))
        recipients = sorted(m.to for m in mail.outbox)
        assert recipients == [
            ["alice@example.com"],
            ["bob@example.com"],
        ]

    @pytest.mark.django_db(transaction=True)
    def test_notify__skips_members_without_email(self, org):
        from django.contrib.auth.models import User
        from django.core import mail

        from accounts.models import Membership
        from services.email.mx.models import IncomingMessage
        from services.email.mx.tasks import notify_postmaster_recipients

        no_email_user = User.objects.create_user(
            username="carol", email="", password="test"
        )
        Membership.objects.create(
            org=org, user=no_email_user, role=Membership.Role.WRITE
        )
        msg = IncomingMessage.objects.create(
            org=org,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        with override_settings(EMAIL_BACKEND=LOCMEM):
            notify_postmaster_recipients.func(message_pk=str(msg.id))
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["alice@example.com"]

    @pytest.mark.django_db(transaction=True)
    def test_notify__includes_detail_url_in_body(self, org, user):
        from django.conf import settings
        from django.core import mail

        from services.email.mx.models import IncomingMessage
        from services.email.mx.tasks import notify_postmaster_recipients

        msg = IncomingMessage.objects.create(
            org=org,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        with override_settings(EMAIL_BACKEND=LOCMEM):
            notify_postmaster_recipients.func(message_pk=str(msg.id))
        expected_url = (
            f"http://{settings.RELAY_PLATFORM_DOMAIN}{msg.get_absolute_url()}"
        )
        assert expected_url in mail.outbox[0].body

    @pytest.mark.django_db(transaction=True)
    def test_notify__logs_error_on_smtp_failure(self, org, user, caplog):
        import logging
        from unittest.mock import patch

        from services.email.mx.models import IncomingMessage
        from services.email.mx.tasks import notify_postmaster_recipients

        msg = IncomingMessage.objects.create(
            org=org,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        with (
            override_settings(EMAIL_BACKEND=LOCMEM),
            patch(
                "django.contrib.auth.models.User.email_user",
                side_effect=OSError("Connection refused"),
            ),
            caplog.at_level(logging.ERROR),
        ):
            notify_postmaster_recipients.func(message_pk=str(msg.id))
        assert any(
            "Postmaster notification" in r.message and "failed" in r.message
            for r in caplog.records
        )
