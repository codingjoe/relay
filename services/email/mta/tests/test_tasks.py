import datetime
import itertools
import json
import time
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.files.base import ContentFile

from accounts.models import Membership, Organization
from domains.models import Domain
from kms.models import SigningKey
from services.email.mta.models import (
    IncomingMessage,
    TlsFailure,
    TlsReport,
    Webhook,
    WebhookDelivery,
)
from services.email.mta.tasks import (
    WEBHOOK_RETRY_DELAYS,
    WebhookDeliveryError,
    WebhookEvent,
    WebhookJSONEncoder,
    deliver_to_webhook,
    deliver_webhook,
    dispatch_webhook,
    mark_failed_if_pending,
    notify_postmaster_recipients,
    parse_tls_report,
    webhook_retry,
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

    def test_default__raises_type_error_for_unsupported_type(self):
        with pytest.raises(TypeError):
            json.dumps({"event": object()}, cls=WebhookJSONEncoder)


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
    def test_notify__logs_and_continues_when_sending_fails(self, org):
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
        with patch.object(User, "email_user", side_effect=OSError("smtp down")):
            notify_postmaster_recipients.func(message_pk=str(msg.id))

        assert len(mail.outbox) == 0


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


def make_webhook(org, address_pattern="*", is_active=True):
    return Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="Hook",
        address_pattern=address_pattern,
        domain=Domain.objects.get(org=org),
        signing_key=SigningKey.generate("ed25519"),
        is_active=is_active,
    )


def make_webhook_retry_context(attempt, message_id=None):
    kwargs = {"message_id": message_id} if message_id else {}
    return SimpleNamespace(attempt=attempt, task_result=SimpleNamespace(kwargs=kwargs))


class TestWebhookRetry:
    def test_webhook_retry__returns_delay_for_next_attempt(self):
        delay = webhook_retry(make_webhook_retry_context(attempt=0))
        assert delay is not None
        assert (
            WEBHOOK_RETRY_DELAYS[1]
            <= delay.total_seconds()
            < WEBHOOK_RETRY_DELAYS[1] + 30
        )

    def test_webhook_retry__ignores_missing_message_id(self):
        context = make_webhook_retry_context(attempt=len(WEBHOOK_RETRY_DELAYS) - 1)
        assert webhook_retry(context) is None

    @pytest.mark.django_db(transaction=True)
    def test_webhook_retry__marks_message_failed_after_final_attempt(self, org):
        message = make_incoming_message(org)

        context = make_webhook_retry_context(
            attempt=len(WEBHOOK_RETRY_DELAYS) - 1, message_id=str(message.pk)
        )

        assert webhook_retry(context) is None
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.WEBHOOK_FAILED


@pytest.mark.django_db(transaction=True)
class TestMarkFailedIfPending:
    def test_marks_received_message_as_failed(self, org):
        message = make_incoming_message(org)

        mark_failed_if_pending(str(message.pk))

        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.WEBHOOK_FAILED

    def test_leaves_quarantined_message_untouched(self, org):
        message = make_incoming_message(org, status=IncomingMessage.Status.QUARANTINED)

        mark_failed_if_pending(str(message.pk))

        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.QUARANTINED


@pytest.mark.django_db(transaction=True)
class TestDispatchWebhook:
    def test_drops_message_without_matching_webhook(self, org):
        message = make_incoming_message(org)

        dispatch_webhook.func(message_id=str(message.pk))

        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.DROPPED

    def test_enqueues_delivery_for_matching_webhook(self, org):
        message = make_incoming_message(org)
        webhook = make_webhook(org)

        with patch("services.email.mta.tasks.deliver_webhook") as mock_deliver:
            dispatch_webhook.func(message_id=str(message.pk))

        mock_deliver.enqueue.assert_called_once_with(
            message_id=str(message.pk), webhook_id=str(webhook.pk)
        )
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.RECEIVED

    def test_drops_message_without_active_billing(self, org, monkeypatch):
        message = make_incoming_message(org)
        make_webhook(org)
        monkeypatch.setattr(Organization, "billing_is_active", False)

        with patch("services.email.mta.tasks.deliver_webhook") as mock_deliver:
            dispatch_webhook.func(message_id=str(message.pk))

        mock_deliver.enqueue.assert_not_called()
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.DROPPED


@pytest.mark.django_db(transaction=True)
class TestDeliverWebhook:
    def test_inactive_webhook_marks_message_failed(self, org):
        message = make_incoming_message(org)
        webhook = make_webhook(org, is_active=False)

        with patch("services.email.mta.tasks.httpx.post") as mock_post:
            deliver_webhook.func(message_id=str(message.pk), webhook_id=str(webhook.pk))

        mock_post.assert_not_called()
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.WEBHOOK_FAILED

    def test_success_records_sent_delivery_and_marks_message(self, org):
        message = make_incoming_message(org)
        webhook = make_webhook(org)
        response = Mock(is_success=True, status_code=200, text="ok")

        with patch("services.email.mta.tasks.httpx.post", return_value=response):
            deliver_webhook.func(message_id=str(message.pk), webhook_id=str(webhook.pk))

        delivery = WebhookDelivery.objects.get(message=message)
        assert delivery.status == WebhookDelivery.Status.SENT
        assert delivery.response_code == 200
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.WEBHOOK_SENT
        webhook.refresh_from_db()
        assert webhook.last_used_at is not None

    def test_gone_deactivates_webhook_and_marks_message_failed(self, org):
        message = make_incoming_message(org)
        webhook = make_webhook(org)
        response = Mock(is_success=False, status_code=410, text="gone")

        with patch("services.email.mta.tasks.httpx.post", return_value=response):
            deliver_webhook.func(message_id=str(message.pk), webhook_id=str(webhook.pk))

        delivery = WebhookDelivery.objects.get(message=message)
        assert delivery.status == WebhookDelivery.Status.FAILED
        assert delivery.response_code == 410
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.WEBHOOK_FAILED
        webhook.refresh_from_db()
        assert webhook.is_active is False

    def test_server_error_raises_webhook_delivery_error(self, org):
        message = make_incoming_message(org)
        webhook = make_webhook(org)
        response = Mock(is_success=False, status_code=500, text="boom")

        with (
            patch("services.email.mta.tasks.httpx.post", return_value=response),
            pytest.raises(WebhookDeliveryError),
        ):
            deliver_webhook.func(message_id=str(message.pk), webhook_id=str(webhook.pk))

        delivery = WebhookDelivery.objects.get(message=message)
        assert delivery.status == WebhookDelivery.Status.FAILED
        assert delivery.response_code == 500
        message.refresh_from_db()
        assert message.status == IncomingMessage.Status.RECEIVED


@pytest.mark.django_db(transaction=True)
class TestDeliverToWebhook:
    def test_connection_error_records_failed_delivery(self, org):
        message = make_incoming_message(org)
        webhook = make_webhook(org)

        with patch(
            "services.email.mta.tasks.httpx.post",
            side_effect=httpx.ConnectError("connection refused"),
        ):
            ok, status_code = deliver_to_webhook(message, webhook)

        assert ok is False
        assert status_code == 0
        delivery = WebhookDelivery.objects.get(message=message)
        assert delivery.status == WebhookDelivery.Status.FAILED
        assert "connection refused" in delivery.response_body
        assert delivery.response_code is None


TLS_RPT_REPORT = {
    "organization-name": "Acme Corp",
    "contact-info": "mailto:tlsreports@acme.com",
    "report-id": "2026-01-15T00:00:00Z_acme",
    "date-range": {
        "start-datetime": "2026-01-14T00:00:00Z",
        "end-datetime": "2026-01-15T00:00:00Z",
    },
    "policies": [
        {
            "policy": {"policy-type": "sts", "policy-domain": "example.com"},
            "summary": {"successful-session-count": 5, "failed-session-count": 2},
            "failure-details": [
                {
                    "result-type": "certificate-name-mismatch",
                    "sending-mta-ip": "192.0.2.10",
                    "receiving-mx-hostname": "mx1.example.com",
                    "receiving-mx-ip": "192.0.2.1",
                    "failed-session-count": 2,
                    "additional-information": "https://acme.com/why",
                }
            ],
        }
    ],
}


def make_tls_report_email():
    email = EmailMessage()
    email["From"] = "tlsreports@acme.com"
    email["To"] = "tls-rpt@example.com"
    email["Subject"] = "Report Domain: example.com"
    email.set_content("Report attached.")
    email.add_attachment(
        json.dumps(TLS_RPT_REPORT).encode(),
        maintype="application",
        subtype="json",
        filename="report.json",
    )
    return email


@pytest.mark.django_db(transaction=True)
class TestParseTlsReport:
    def test_stores_report_metadata_and_failures(self, org):
        message = make_incoming_message(org)
        report = TlsReport(
            org=org,
            domain=message.domain,
            receiving_domain="example.com",
            mail_from="tlsreports@acme.com",
            rcpt_to="tls-rpt@example.com",
            subject="Report Domain: example.com",
            message_id="<tls@example.com>",
            report_id="",
        )
        report.raw_body.save("tls.eml", ContentFile(make_tls_report_email().as_bytes()))
        report.save()

        parse_tls_report.func(report_pk=str(report.pk))

        report.refresh_from_db()
        assert report.reporting_org == "Acme Corp"
        assert report.reporting_email == "mailto:tlsreports@acme.com"
        assert report.report_id == "2026-01-15T00:00:00Z_acme"
        assert report.begin_at == datetime.datetime(2026, 1, 14, tzinfo=datetime.UTC)
        assert report.end_at == datetime.datetime(2026, 1, 15, tzinfo=datetime.UTC)
        assert report.successful_session_count == 5
        assert report.failed_session_count == 2
        failure = TlsFailure.objects.get(report=report)
        assert failure.policy_type == "sts"
        assert failure.policy_domain == "example.com"
        assert failure.result_type == "certificate-name-mismatch"
        assert failure.sending_mta_ip_address == "192.0.2.10"
        assert failure.receiving_mx_hostname == "mx1.example.com"
        assert failure.receiving_mx_ip_address == "192.0.2.1"
        assert failure.count == 2
        assert failure.additional_info == "https://acme.com/why"
