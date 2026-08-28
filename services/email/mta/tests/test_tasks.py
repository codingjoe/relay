import itertools
import json
import time
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile

from accounts.models import Membership
from domains.models import Domain
from services.email.mta.models import IncomingMessage
from services.email.mta.tasks import (
    WEBHOOK_RETRY_DELAYS,
    WebhookEvent,
    WebhookJSONEncoder,
    notify_postmaster_recipients,
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
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        msg = IncomingMessage(
            org=org,
            domain=domain,
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
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        msg = IncomingMessage.objects.create(
            org=org,
            domain=domain,
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


class TestNotifyPostmasterRecipients:
    @pytest.mark.django_db(transaction=True)
    def test_notify__sends_to_all_members_with_email(self, org, user, other_user):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        msg = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        notify_postmaster_recipients.func(message_pk=str(msg.id))
        recipients = sorted(m.to for m in mail.outbox)
        assert recipients == [
            ["alice@example.com"],
            ["bob@example.com"],
        ]

    @pytest.mark.django_db(transaction=True)
    def test_notify__skips_members_without_email(self, org):
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        no_email_user = User.objects.create_user(
            username="carol", email="", password="test"
        )
        Membership.objects.create(
            org=org, user=no_email_user, role=Membership.Role.WRITE
        )
        msg = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        notify_postmaster_recipients.func(message_pk=str(msg.id))
        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == ["alice@example.com"]

    @pytest.mark.django_db(transaction=True)
    def test_notify__includes_detail_url_in_body(self, org, user):
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        msg = IncomingMessage.objects.create(
            org=org,
            domain=domain,
            receiving_domain="example.com",
            mail_from="external@example.org",
            rcpt_to="postmaster@example.com",
            subject="Alert",
            message_id="<abc@example.org>",
        )
        notify_postmaster_recipients.func(message_pk=str(msg.id))
        expected_url = (
            f"http://{settings.RELAY_PLATFORM_DOMAIN}{msg.get_absolute_url()}"
        )
        assert expected_url in mail.outbox[0].body


def make_incoming_message(org, status=IncomingMessage.Status.RECEIVED):
    domain = Domain.objects.get(org=org)
    msg = IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain="example.com",
        mail_from="spam@acme.com",
        rcpt_to="inbox@example.com",
        status=status,
    )
    msg.raw_body.save("test.eml", ContentFile(b"spam body"), save=False)
    msg.save()
    return msg


@pytest.mark.django_db(transaction=True)
class TestCheckIncomingSpam:
    def test_check_incoming_spam__quarantines_spam(self, org):
        from services.email.mta.tasks import check_incoming_spam
        from services.email.spam import SpamAction, SpamResult

        msg = make_incoming_message(org)
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=20.0, action=SpamAction.REJECT),
            ),
            patch("services.email.mta.tasks.dispatch_webhook") as mock_webhook,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        msg.refresh_from_db()
        assert msg.status == IncomingMessage.Status.QUARANTINED
        assert msg.spam_score == 20.0
        mock_webhook.enqueue.assert_not_called()
        assert len(mail.outbox) == 0

    def test_check_incoming_spam__dispatches_webhook_for_clean_message(self, org):
        from services.email.mta.tasks import check_incoming_spam
        from services.email.spam import SpamResult

        msg = make_incoming_message(org)
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook") as mock_webhook,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        msg.refresh_from_db()
        assert msg.status == IncomingMessage.Status.RECEIVED
        mock_webhook.enqueue.assert_called_once_with(message_id=str(msg.pk))

    def test_check_incoming_spam__skips_webhook_for_already_quarantined(self, org):
        from services.email.mta.tasks import check_incoming_spam
        from services.email.spam import SpamResult

        msg = make_incoming_message(org, status=IncomingMessage.Status.QUARANTINED)
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook") as mock_webhook,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        msg.refresh_from_db()
        assert msg.status == IncomingMessage.Status.QUARANTINED
        mock_webhook.enqueue.assert_not_called()
