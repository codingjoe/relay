from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django.urls import resolve, reverse

from domains.models import Domain
from services.email.message.models import Message
from services.email.msa.models import OutgoingMessage
from services.email.mta.models import IncomingMessage


def create_outgoing(user, org, status=None):
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    msg = OutgoingMessage.objects.create(
        org=org,
        domain=domain,
        rcpt_to="bob@example.com",
        mail_from="alice@example.com",
    )
    if status is not None:
        msg.status = status
        msg.save(update_fields=["status"])
    return msg


def descendants(model):
    """Yield every concrete descendant of `model`."""
    for sub in model.__subclasses__():
        yield sub
        yield from descendants(sub)


def create_incoming(org, status=None):
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    msg = IncomingMessage.objects.create(
        org=org,
        domain=domain,
        rcpt_to="bob@app.acme.com",
        mail_from="alice@external.com",
        receiving_domain="app.acme.com",
    )
    if status is not None:
        msg.status = status
        msg.save(update_fields=["status"])
    return msg


class TestOutgoingMessageStatus:
    def test_badge_variant__sent(self):
        assert OutgoingMessage.Status.SENT.badge_variant == "primary"

    def test_badge_variant__delivered(self):
        assert OutgoingMessage.Status.DELIVERED.badge_variant == "primary"

    def test_badge_variant__bounced(self):
        assert OutgoingMessage.Status.BOUNCED.badge_variant == "destructive"

    def test_badge_variant__dropped(self):
        assert OutgoingMessage.Status.DROPPED.badge_variant == "destructive"

    def test_badge_variant__failed(self):
        assert OutgoingMessage.Status.FAILED.badge_variant == "destructive"

    def test_badge_variant__pending(self):
        assert OutgoingMessage.Status.PENDING.badge_variant == "outline"

    def test_badge_variant__held(self):
        assert OutgoingMessage.Status.HELD.badge_variant == "outline"


class TestIncomingMessageStatus:
    def test_badge_variant__received(self):
        assert IncomingMessage.Status.RECEIVED.badge_variant == "primary"

    def test_badge_variant__webhook_failed(self):
        assert IncomingMessage.Status.WEBHOOK_FAILED.badge_variant == "destructive"

    def test_badge_variant__dropped(self):
        assert IncomingMessage.Status.DROPPED.badge_variant == "destructive"

    def test_badge_variant__webhook_sent(self):
        assert IncomingMessage.Status.WEBHOOK_SENT.badge_variant == "outline"


class TestMessage:
    @pytest.mark.django_db
    def test_status_display__outgoing_sent(self, user, org):
        msg = create_outgoing(user, org, OutgoingMessage.Status.SENT)
        assert Message.objects.get(pk=msg.pk).status_display == "sent"

    @pytest.mark.django_db
    def test_status_display__outgoing_pending(self, user, org):
        msg = create_outgoing(user, org)
        assert Message.objects.get(pk=msg.pk).status_display == "pending"

    @pytest.mark.django_db
    def test_status_display__incoming_received(self, org):
        msg = create_incoming(org)
        assert Message.objects.get(pk=msg.pk).status_display == "received"

    @pytest.mark.django_db
    def test_status_display__incoming_webhook_sent(self, org):
        msg = create_incoming(org, IncomingMessage.Status.WEBHOOK_SENT)
        assert Message.objects.get(pk=msg.pk).status_display == "webhook sent"

    @pytest.mark.django_db
    def test_status_badge_variant__outgoing_sent(self, user, org):
        msg = create_outgoing(user, org, OutgoingMessage.Status.SENT)
        assert Message.objects.get(pk=msg.pk).status_badge_variant == "primary"

    @pytest.mark.django_db
    def test_status_badge_variant__outgoing_bounced(self, user, org):
        msg = create_outgoing(user, org, OutgoingMessage.Status.BOUNCED)
        assert Message.objects.get(pk=msg.pk).status_badge_variant == "destructive"

    @pytest.mark.django_db
    def test_status_badge_variant__outgoing_pending(self, user, org):
        msg = create_outgoing(user, org)
        assert Message.objects.get(pk=msg.pk).status_badge_variant == "outline"

    @pytest.mark.django_db
    def test_status_badge_variant__incoming_received(self, org):
        msg = create_incoming(org)
        assert Message.objects.get(pk=msg.pk).status_badge_variant == "primary"

    @pytest.mark.django_db
    def test_status_badge_variant__incoming_webhook_failed(self, org):
        msg = create_incoming(org, IncomingMessage.Status.WEBHOOK_FAILED)
        assert Message.objects.get(pk=msg.pk).status_badge_variant == "destructive"

    @pytest.mark.django_db
    def test_status_badge_variant__incoming_webhook_sent(self, org):
        msg = create_incoming(org, IncomingMessage.Status.WEBHOOK_SENT)
        assert Message.objects.get(pk=msg.pk).status_badge_variant == "outline"

    @pytest.mark.django_db
    def test_kind__outgoing(self, user, org):
        msg = create_outgoing(user, org)
        assert Message.objects.get(pk=msg.pk).kind == "outgoingmessage"

    @pytest.mark.django_db
    def test_kind__incoming(self, org):
        msg = create_incoming(org)
        assert Message.objects.get(pk=msg.pk).kind == "incomingmessage"

    @pytest.mark.django_db
    def test_kind_icon__outgoing(self, user, org):
        msg = create_outgoing(user, org)
        assert Message.objects.get(pk=msg.pk).kind_icon == "send"

    @pytest.mark.django_db
    def test_kind_icon__incoming(self, org):
        msg = create_incoming(org)
        assert Message.objects.get(pk=msg.pk).kind_icon == "inbox"

    @pytest.mark.django_db
    def test_domain_name__returns_domain_name(self, user, org):
        msg = create_outgoing(user, org)
        assert Message.objects.get(pk=msg.pk).domain_name == str(msg.domain)

    @pytest.mark.django_db
    def test_domain_name__incoming_uses_receiving_domain(self, org):
        msg = create_incoming(org)
        assert msg.domain_name == "app.acme.com"

    @pytest.mark.django_db
    def test_str__includes_from_to_and_kind(self, user, org):
        msg = create_outgoing(user, org)
        rendered = str(Message.objects.get(pk=msg.pk))
        assert "alice@example.com" in rendered
        assert "bob@example.com" in rendered
        assert "outgoingmessage" in rendered

    @pytest.mark.django_db
    def test_get_absolute_url__outgoing(self, user, org):
        msg = create_outgoing(user, org)
        assert str(msg.pk) in Message.objects.get(pk=msg.pk).get_absolute_url()

    @pytest.mark.django_db
    def test_get_absolute_url__incoming(self, org):
        msg = create_incoming(org)
        assert str(msg.pk) in Message.objects.get(pk=msg.pk).get_absolute_url()

    def test_url_name__resolves_for_every_subclass(self):
        for model in descendants(Message):
            url = reverse(
                f"{model._meta.app_label}:{model.url_name}",
                kwargs={"org_slug": "x", "pk": str(uuid4())},
            )
            match = resolve(url)
            assert match.view_name == f"{model._meta.app_label}:{model.url_name}"


class TestMessageHeaders:
    def test_headers_from_raw__parses_name_value_pairs(self):
        raw = b"From: alice@example.com\r\nSubject: Hello\r\n\r\nBody"
        assert Message.headers_from_raw(raw) == [
            ["From", "alice@example.com"],
            ["Subject", "Hello"],
        ]

    def test_headers_from_raw__preserves_duplicate_headers(self):
        raw = b"Received: one\r\nReceived: two\r\n\r\nBody"
        assert Message.headers_from_raw(raw) == [
            ["Received", "one"],
            ["Received", "two"],
        ]

    def test_headers_from_raw__decodes_8bit_header_bytes(self):
        raw = (
            b"From: alice@example.com\r\n"
            b"X-Latin1: caf\xe9\r\n"
            b"X-UTF8: caf\xc3\xa9\r\n"
            b"\r\n"
            b"Body"
        )
        assert Message.headers_from_raw(raw) == [
            ["From", "alice@example.com"],
            ["X-Latin1", "caf\N{REPLACEMENT CHARACTER}"],
            ["X-UTF8", "café"],
        ]

    def test_headers_from_raw__replaces_nul_bytes(self):
        raw = b"From: alice@example.com\r\nX-Custom: a\x00b\r\n\r\nBody"
        assert Message.headers_from_raw(raw) == [
            ["From", "alice@example.com"],
            ["X-Custom", "a\N{REPLACEMENT CHARACTER}b"],
        ]

    @pytest.mark.django_db
    def test_headers_from_raw__serializes_through_jsonfield(self, user, org):
        domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
        raw = b"From: alice@example.com\r\nX-Custom: caf\xc3\xa9\r\n\r\nBody"
        message = OutgoingMessage.objects.create(
            org=org,
            domain=domain,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            headers=OutgoingMessage.headers_from_raw(raw),
        )
        message = OutgoingMessage.objects.get(pk=message.pk)
        assert message.headers == [
            ["From", "alice@example.com"],
            ["X-Custom", "café"],
        ]

    @pytest.mark.django_db
    def test_parsed_headers__uses_stored_headers(self, user, org):
        msg = create_outgoing(user, org)
        msg.headers = [["From", "alice@example.com"], ["Subject", "Hello"]]
        msg.save(update_fields=["headers"])
        assert Message.objects.get(pk=msg.pk).parsed_headers == [
            ["From", "alice@example.com"],
            ["Subject", "Hello"],
        ]

    @pytest.mark.django_db
    def test_parsed_headers__falls_back_to_raw_body(self, user, org):
        msg = create_outgoing(user, org)
        msg.raw_body.save(
            f"{msg.id}.eml",
            ContentFile(b"From: alice@example.com\r\nSubject: Hello\r\n\r\nBody"),
            save=False,
        )
        msg.save(update_fields=["raw_body"])
        assert Message.objects.get(pk=msg.pk).parsed_headers == [
            ["From", "alice@example.com"],
            ["Subject", "Hello"],
        ]
