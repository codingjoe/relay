import pytest

from services.email.message.models import Message
from services.email.mx.models import IncomingMessage
from services.email.smtp.models import OutgoingMessage


def create_outgoing(user, org, status=None):
    msg = OutgoingMessage.objects.create(
        sender=user,
        org=org,
        rcpt_to="bob@example.com",
        mail_from="alice@example.com",
    )
    if status is not None:
        msg.status = status
        msg.save(update_fields=["status"])
    return msg


def create_incoming(org, status=None):
    msg = IncomingMessage.objects.create(
        org=org,
        rcpt_to="bob@app.acme.com",
        mail_from="alice@external.com",
        receiving_domain="app.acme.com",
    )
    if status is not None:
        msg.status = status
        msg.save(update_fields=["status"])
    return msg


class TestOutgoingStatusBadgeVariant:
    @pytest.mark.parametrize(
        "status, expected",
        [
            (OutgoingMessage.Status.SENT, "primary"),
            (OutgoingMessage.Status.DELIVERED, "primary"),
            (OutgoingMessage.Status.BOUNCED, "destructive"),
            (OutgoingMessage.Status.DROPPED, "destructive"),
            (OutgoingMessage.Status.FAILED, "destructive"),
            (OutgoingMessage.Status.PENDING, "outline"),
            (OutgoingMessage.Status.HELD, "outline"),
        ],
    )
    def test_badge_variant__matches_expected(self, status, expected):
        assert status.badge_variant == expected


class TestIncomingStatusBadgeVariant:
    @pytest.mark.parametrize(
        "status, expected",
        [
            (IncomingMessage.Status.RECEIVED, "primary"),
            (IncomingMessage.Status.WEBHOOK_FAILED, "destructive"),
            (IncomingMessage.Status.DROPPED, "destructive"),
            (IncomingMessage.Status.WEBHOOK_SENT, "outline"),
        ],
    )
    def test_badge_variant__matches_expected(self, status, expected):
        assert status.badge_variant == expected


class TestMessageStatusDisplay:
    @pytest.mark.django_db
    def test_status_display__outgoing_sent(self, user, org):
        msg = create_outgoing(user, org, OutgoingMessage.Status.SENT)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_display == "sent"

    @pytest.mark.django_db
    def test_status_display__outgoing_pending(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_display == "pending"

    @pytest.mark.django_db
    def test_status_display__incoming_received(self, org):
        msg = create_incoming(org)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_display == "received"

    @pytest.mark.django_db
    def test_status_display__incoming_webhook_sent(self, org):
        msg = create_incoming(org, IncomingMessage.Status.WEBHOOK_SENT)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_display == "webhook sent"


class TestMessageStatusBadgeVariant:
    @pytest.mark.django_db
    def test_badge_variant__outgoing_sent(self, user, org):
        msg = create_outgoing(user, org, OutgoingMessage.Status.SENT)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_badge_variant == "primary"

    @pytest.mark.django_db
    def test_badge_variant__outgoing_bounced(self, user, org):
        msg = create_outgoing(user, org, OutgoingMessage.Status.BOUNCED)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_badge_variant == "destructive"

    @pytest.mark.django_db
    def test_badge_variant__outgoing_pending(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_badge_variant == "outline"

    @pytest.mark.django_db
    def test_badge_variant__incoming_received(self, org):
        msg = create_incoming(org)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_badge_variant == "primary"

    @pytest.mark.django_db
    def test_badge_variant__incoming_webhook_failed(self, org):
        msg = create_incoming(org, IncomingMessage.Status.WEBHOOK_FAILED)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_badge_variant == "destructive"

    @pytest.mark.django_db
    def test_badge_variant__incoming_webhook_sent(self, org):
        msg = create_incoming(org, IncomingMessage.Status.WEBHOOK_SENT)
        base = Message.objects.get(pk=msg.pk)
        assert base.status_badge_variant == "outline"


class TestMessageKind:
    @pytest.mark.django_db
    def test_kind__outgoing(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        assert base.kind == "outgoingmessage"

    @pytest.mark.django_db
    def test_kind__incoming(self, org):
        msg = create_incoming(org)
        base = Message.objects.get(pk=msg.pk)
        assert base.kind == "incomingmessage"


class TestMessageKindIcon:
    @pytest.mark.django_db
    def test_kind_icon__outgoing_is_send(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        assert base.kind_icon == "send"

    @pytest.mark.django_db
    def test_kind_icon__incoming_is_inbox(self, org):
        msg = create_incoming(org)
        base = Message.objects.get(pk=msg.pk)
        assert base.kind_icon == "inbox"


class TestMessageDomainName:
    @pytest.mark.django_db
    def test_domain_name__empty_when_no_domain(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        assert base.domain_name == ""

    @pytest.mark.django_db
    def test_domain_name__incoming_uses_receiving_domain(self, org):
        msg = create_incoming(org)
        assert msg.domain_name == "app.acme.com"


class TestMessageStr:
    @pytest.mark.django_db
    def test_str__includes_from_to_and_kind(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        rendered = str(base)
        assert "alice@example.com" in rendered
        assert "bob@example.com" in rendered
        assert "outgoingmessage" in rendered


class TestMessageGetAbsoluteUrl:
    @pytest.mark.django_db
    def test_get_absolute_url__outgoing(self, user, org):
        msg = create_outgoing(user, org)
        base = Message.objects.get(pk=msg.pk)
        url = base.get_absolute_url()
        assert str(msg.pk) in url

    @pytest.mark.django_db
    def test_get_absolute_url__incoming(self, org):
        msg = create_incoming(org)
        base = Message.objects.get(pk=msg.pk)
        url = base.get_absolute_url()
        assert str(msg.pk) in url
