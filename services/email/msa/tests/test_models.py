import pytest
from django.contrib.auth.models import User

from accounts.models import Organization
from domains.models import Domain
from services.email.msa.models import MsaCredential, OutgoingMessage, Transmission


def make_message(org, user, **kwargs):
    """Create an OutgoingMessage with the org's managed domain."""
    domain = Domain.objects.filter(org=org).first()  # noqa: multiple domains per org
    defaults = {
        "org": org,
        "rcpt_to": "bob@example.com",
        "mail_from": "alice@example.com",
        "domain": domain,
    }
    defaults.update(kwargs)
    return OutgoingMessage.objects.create(**defaults)


@pytest.mark.django_db
class TestOutgoingMessageStr:
    def test_str__shows_from_to_and_status(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="o")
        msg = make_message(
            org, user, subject="Hello", status=OutgoingMessage.Status.PENDING
        )
        assert "alice@example.com" in str(msg)
        assert "bob@example.com" in str(msg)
        assert "pending" in str(msg)


@pytest.mark.django_db
class TestOutgoingMessageDefaults:
    def test_default_status__pending(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="o")
        msg = make_message(org, user)
        assert msg.status == OutgoingMessage.Status.PENDING

    def test_default_received_with_tls__false(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="o")
        msg = make_message(org, user)
        assert msg.received_with_tls is False


@pytest.mark.django_db
class TestTransmissionStr:
    def test_str__includes_message_and_status(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="o")
        msg = make_message(org, user)
        t = Transmission.objects.create(message=msg, status=Transmission.Status.SENT)
        assert str(msg) in str(t)
        assert "sent" in str(t)


@pytest.mark.django_db
class TestMsaCredential:
    def test_type__defaults_to_smtp(self):
        org = Organization.objects.create(slug="o")
        cred, _ = MsaCredential.objects.create_with_key(org=org)
        assert cred.type == MsaCredential.Type.SMTP

    def test_inherits_credential__has_key_fields(self):
        org = Organization.objects.create(slug="o")
        cred, raw_key = MsaCredential.objects.create_with_key(org=org, name="prod")
        assert cred.key_hash
        assert cred.key_prefix == raw_key[:8]
        assert cred.salt == "services.email.msa.models.MsaCredential"
        assert cred.org == org

    def test_str__shows_org_and_name(self):
        org = Organization.objects.create(slug="acme")
        cred, _ = MsaCredential.objects.create_with_key(org=org, name="prod")
        assert "acme" in str(cred)
        assert "prod" in str(cred)


@pytest.mark.django_db
class TestOutgoingMessageGetAbsoluteUrl:
    def test_get_absolute_url__returns_detail_url(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(slug="acme")
        msg = make_message(org, user)
        url = msg.get_absolute_url()
        assert url is not None
        assert f"/org/{org.slug}/email/messages/{msg.id}" in url


class TestTransmission:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (Transmission.Status.SENT, "primary"),
            (Transmission.Status.FAILED, "destructive"),
            (Transmission.Status.BOUNCED, "destructive"),
            (Transmission.Status.RETRY, "outline"),
        ],
    )
    def test_status_badge_variant(self, status, expected):
        assert Transmission(status=status).status_badge_variant == expected
