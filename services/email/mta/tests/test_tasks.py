import datetime
import itertools
import json
import time
from email import message_from_bytes, policy
from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.utils import timezone, translation
from django_letter.exceptions import EmailImproperlyConfigured

from accounts.models import Membership, Organization
from domains.models import Domain
from kms.models import SigningKey
from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage
from services.email.mta.emails import PostmasterForwardEmail
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
    check_incoming_spam,
    deliver_to_webhook,
    deliver_webhook,
    dispatch_webhook,
    forward_postmaster_message,
    mark_failed_if_pending,
    parse_tls_report,
    webhook_retry,
)
from services.email.spam.client import SpamAction, SpamResult


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
        )
        msg.raw_body.save("test.eml", ContentFile(b"raw bytes"), save=False)
        msg.save()
        Transmission.objects.create(
            message=msg,
            status=Transmission.Status.RECEIVED,
            tls_mode=Transmission.TlsMode.TLS,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )

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


POSTMASTER_RAW_BODY = (
    b"From: author@example.org\r\nSubject: Alert\r\n\r\nSomething happened\r\n"
)
RAW_BODY_WITHOUT_SENDER = b"Subject: Alert\r\n\r\nSomething happened\r\n"
RAW_BODY_WITH_ENCODED_SENDER = (
    b"From: =?utf-8?q?J=C3=B6rg_M=C3=BCller?= <joerg@example.org>\r\n"
    b"Subject: Alert\r\n\r\nSomething happened\r\n"
)


@pytest.fixture
def base_url(settings):
    """Return the host the package derives the base URL from."""
    settings.ALLOWED_HOSTS = ["relay.example"]
    return "https://relay.example"


def make_forward_email(message, **kwargs):
    """Build a forward the way a sending caller does, language included."""
    kwargs.setdefault("language", translation.get_language())
    return PostmasterForwardEmail(message, **kwargs)


def make_postmaster_message(
    org, raw_body=POSTMASTER_RAW_BODY, mail_from="bounce@example.org"
):
    message = IncomingMessage(
        org=org,
        domain=Domain.objects.get(org=org),
        receiving_domain="example.com",
        mail_from=mail_from,
        rcpt_to="postmaster@example.com",
        subject="Alert",
    )
    message.raw_body.save("test.eml", ContentFile(raw_body), save=False)
    message.save()
    return message


def forwarded_copy(message):
    return message_from_bytes(
        OutgoingMessage.objects.get(
            org=message.org, rcpt_to="alice@example.com"
        ).raw_body.read(),
        policy=policy.default,
    )


@pytest.mark.django_db(transaction=True)
class TestForwardPostmasterMessage:
    @pytest.fixture(autouse=True)
    def spam_check(self, monkeypatch):
        """Keep the queued spam scans off rspamd."""
        check = Mock()
        monkeypatch.setattr("services.email.msa.handlers.check_outgoing_spam", check)
        return check

    def test_forward_postmaster_message__submits_a_copy_per_member_with_email(
        self, org, other_user
    ):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        copies = OutgoingMessage.objects.filter(org=org)
        assert sorted(copy.rcpt_to for copy in copies) == [
            "alice@example.com",
            "bob@example.com",
        ]

    def test_forward_postmaster_message__skips_members_without_email(self, org):
        carol = User.objects.create_user(username="carol", email="")
        Membership.objects.create(org=org, user=carol, role=Membership.Role.WRITE)
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert [copy.rcpt_to for copy in OutgoingMessage.objects.filter(org=org)] == [
            "alice@example.com"
        ]

    def test_forward_postmaster_message__sends_from_the_receiving_domain(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert forwarded_copy(message)["From"] == "postmaster@example.com"

    def test_forward_postmaster_message__attributes_the_copy_to_the_org_domain(
        self, org
    ):
        """The organization's own domain is what bills the copy."""
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        copy = OutgoingMessage.objects.get(org=org)
        assert copy.domain_id == message.domain_id
        assert copy.status == OutgoingMessage.Status.PENDING

    def test_forward_postmaster_message__prefixes_original_subject(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert forwarded_copy(message)["Subject"] == f"Fwd: {message.subject}"

    def test_forward_postmaster_message__body_names_recipient(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        body = forwarded_copy(message).get_body(preferencelist=("plain",)).get_content()
        assert (
            "A message sent to postmaster@example.com was forwarded to your organization."
            in body
        )

    def test_forward_postmaster_message__body_links_to_stored_message(
        self, org, base_url
    ):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        body = forwarded_copy(message).get_body(preferencelist=("plain",)).get_content()
        assert f"{base_url}{message.get_absolute_url()}" in body

    def test_forward_postmaster_message__stores_html_and_plain_parts(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        copy = forwarded_copy(message)
        parts = {part.get_content_type() for part in copy.iter_parts()}
        assert parts == {"text/html", "text/plain"}

    def test_forward_postmaster_message__replies_to_original_author(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert forwarded_copy(message)["Reply-To"] == "author@example.org"

    def test_forward_postmaster_message__replies_to_envelope_sender_without_from_header(
        self, org
    ):
        message = make_postmaster_message(org, raw_body=RAW_BODY_WITHOUT_SENDER)

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert forwarded_copy(message)["Reply-To"] == "bounce@example.org"

    def test_forward_postmaster_message__omits_reply_to_without_sender(self, org):
        message = make_postmaster_message(
            org, raw_body=RAW_BODY_WITHOUT_SENDER, mail_from=""
        )

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert forwarded_copy(message)["Reply-To"] is None

    def test_forward_postmaster_message__signs_and_stamps_the_copy(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        copy = OutgoingMessage.objects.get(org=org)
        assert any(name == "DKIM-Signature" for name, _ in copy.headers)
        assert copy.feedback_id.startswith(f"{org.pk}::")

    def test_forward_postmaster_message__records_the_submission(self, org):
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        transmission = Transmission.objects.get(message__org=org)
        assert transmission.status == Transmission.Status.SUBMITTED

    def test_forward_postmaster_message__queues_every_copy_for_delivery(
        self, org, other_user, spam_check
    ):
        Membership.objects.create(org=org, user=other_user, role=Membership.Role.WRITE)
        message = make_postmaster_message(org)

        forward_postmaster_message.func(message_pk=str(message.pk))

        assert sorted(
            call.kwargs["message_pk"] for call in spam_check.enqueue.call_args_list
        ) == sorted(
            str(pk)
            for pk in OutgoingMessage.objects.filter(org=org).values_list(
                "pk", flat=True
            )
        )


@pytest.mark.django_db
class TestPostmasterForwardEmail:
    def test_render__html_alternative_names_sender_subject_and_recipient(self, org):
        message = make_postmaster_message(org)
        email = make_forward_email(message, to=["alice@example.com"])

        email.render()

        assert [mimetype for _, mimetype in email.alternatives] == ["text/html"]
        html = email.alternatives[0][0]
        assert ">author@example.org<" in html
        assert ">Alert<" in html
        assert ">postmaster@example.com<" in html

    def test_render__links_to_stored_message_in_html_and_body(self, org, base_url):
        message = make_postmaster_message(org)
        email = make_forward_email(message, to=["alice@example.com"])

        email.render()

        detail_url = f"{base_url}{message.get_absolute_url()}"
        assert f'href="{detail_url}"' in email.alternatives[0][0]
        assert detail_url in email.body

    def test_render_preview__uses_sample_values_without_message(self, base_url):
        email = PostmasterForwardEmail.render_preview()

        assert email.subject == "Fwd: Delivery delayed"
        assert f'<html lang="{settings.LANGUAGE_CODE}">' in email.html
        assert ">sender@example.org<" in email.html
        assert ">Delivery delayed<" in email.html
        assert f">postmaster@{settings.RELAY_PLATFORM_DOMAIN}<" in email.html
        assert f"{base_url}{email.incoming_message.get_absolute_url()}" in email.body
        assert not IncomingMessage.objects.exists()

    def test_render_preview__uses_given_message(self, org):
        message = make_postmaster_message(org)

        email = PostmasterForwardEmail.render_preview(message=message)

        assert email.subject == "Fwd: Alert"
        assert ">author@example.org<" in email.html
        assert "Delivery delayed" not in email.html

    def test_render_preview__language_argument_wins(self, org):
        message = make_postmaster_message(org)

        email = PostmasterForwardEmail.render_preview(message=message, language="de")

        assert email.language == "de"
        assert '<html lang="de">' in email.html

    def test_init__base_url_argument_wins(self, org):
        message = make_postmaster_message(org)

        email = make_forward_email(
            message, to=["alice@example.com"], base_url="https://mail.example.org"
        )
        email.render()

        assert (
            f'href="https://mail.example.org{message.get_absolute_url()}"'
            in email.alternatives[0][0]
        )

    def test_init__has_no_language_default(self, org):
        """The sending caller resolves the language, not the class."""
        message = make_postmaster_message(org)

        with pytest.raises(EmailImproperlyConfigured):
            PostmasterForwardEmail(message, to=["alice@example.com"])

    def test_init__decodes_encoded_from_header(self, org):
        message = make_postmaster_message(org, raw_body=RAW_BODY_WITH_ENCODED_SENDER)

        email = make_forward_email(message, to=["alice@example.com"])

        assert email.reply_to == ["Jörg Müller <joerg@example.org>"]


def make_incoming_message(
    org, status=IncomingMessage.Status.RECEIVED, rcpt_to="inbox@example.com"
):
    domain = Domain.objects.get(org=org)
    msg = IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain="example.com",
        mail_from="spam@acme.com",
        rcpt_to=rcpt_to,
        status=status,
    )
    msg.raw_body.save("test.eml", ContentFile(b"spam body"), save=False)
    msg.save()
    return msg


@pytest.mark.django_db(transaction=True)
class TestCheckIncomingSpam:
    def test_check_incoming_spam__quarantines_spam(self, org):
        msg = make_incoming_message(org, rcpt_to="postmaster@example.com")
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=20.0, action=SpamAction.REJECT),
            ),
            patch("services.email.mta.tasks.dispatch_webhook") as mock_webhook,
            patch(
                "services.email.mta.tasks.forward_postmaster_message"
            ) as mock_forward,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        msg.refresh_from_db()
        assert msg.status == IncomingMessage.Status.QUARANTINED
        assert msg.spam_score == 20.0
        mock_webhook.enqueue.assert_not_called()
        mock_forward.enqueue.assert_not_called()

    def test_check_incoming_spam__dispatches_webhook_for_clean_message(self, org):
        msg = make_incoming_message(org)
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook") as mock_webhook,
            patch(
                "services.email.mta.tasks.forward_postmaster_message"
            ) as mock_forward,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        msg.refresh_from_db()
        assert msg.status == IncomingMessage.Status.RECEIVED
        mock_webhook.enqueue.assert_called_once_with(message_id=str(msg.pk))
        mock_forward.enqueue.assert_not_called()

    def test_check_incoming_spam__forwards_postmaster_message(self, org):
        msg = make_incoming_message(org, rcpt_to="postmaster@example.com")
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook"),
            patch(
                "services.email.mta.tasks.forward_postmaster_message"
            ) as mock_forward,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        mock_forward.enqueue.assert_called_once_with(message_pk=str(msg.pk))

    def test_check_incoming_spam__forwards_postmaster_extension(self, org):
        msg = make_incoming_message(org, rcpt_to="postmaster+bounces@example.com")
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook"),
            patch(
                "services.email.mta.tasks.forward_postmaster_message"
            ) as mock_forward,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        mock_forward.enqueue.assert_called_once_with(message_pk=str(msg.pk))

    def test_check_incoming_spam__forwards_uppercase_postmaster_recipient(self, org):
        msg = make_incoming_message(org, rcpt_to="POSTMASTER@example.com")
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook"),
            patch(
                "services.email.mta.tasks.forward_postmaster_message"
            ) as mock_forward,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        mock_forward.enqueue.assert_called_once_with(message_pk=str(msg.pk))

    def test_check_incoming_spam__skips_handling_for_dmarc_quarantine(self, org):
        msg = make_incoming_message(
            org,
            status=IncomingMessage.Status.QUARANTINED,
            rcpt_to="postmaster@example.com",
        )
        with (
            patch(
                "services.email.mta.tasks.check_message",
                return_value=SpamResult(score=0.0),
            ),
            patch("services.email.mta.tasks.dispatch_webhook") as mock_webhook,
            patch(
                "services.email.mta.tasks.forward_postmaster_message"
            ) as mock_forward,
        ):
            check_incoming_spam.func(message_pk=str(msg.pk), client_ip="")

        msg.refresh_from_db()
        assert msg.status == IncomingMessage.Status.QUARANTINED
        mock_webhook.enqueue.assert_not_called()
        mock_forward.enqueue.assert_not_called()


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
