import secrets

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

    def test_set_key__stores_hash_and_prefix(self):
        cred = MsaCredential(org=Organization.objects.create(slug="o"))
        raw_key = secrets.token_urlsafe(15)
        cred.set_key(raw_key)
        assert cred.key_hash != raw_key
        assert cred.key_prefix == raw_key[:8]

    def test_verify_key__correct_key(self):
        org = Organization.objects.create(slug="o")
        cred, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        assert cred.last_used_at is None
        assert cred.verify_key(raw_key) is True
        cred.refresh_from_db()
        assert cred.last_used_at is not None

    def test_verify_key__wrong_key(self):
        org = Organization.objects.create(slug="o")
        cred, _raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        assert cred.verify_key("wrong-key-12345678") is False

    def test_verify_key__does_not_update_last_used_on_failure(self):
        org = Organization.objects.create(slug="o")
        cred, _raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        cred.verify_key("wrong-key-12345678")
        cred.refresh_from_db()
        assert cred.last_used_at is None

    def test_hold__excluded_from_query(self, user, org):
        cred, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        cred.hold = True
        cred.save(update_fields=["hold"])
        qs = MsaCredential.objects.select_related("org").filter(
            key_prefix=raw_key[:8],
            org__memberships__user__username=user.username,
            type__in=[MsaCredential.Type.SMTP, MsaCredential.Type.SMTP_IP],
            hold=False,
        )
        assert not qs.exists()

    def test_not_hold__included_in_query(self, user, org):
        _cred, raw_key = MsaCredential.objects.create_with_key(org=org, name="test")
        qs = MsaCredential.objects.select_related("org").filter(
            key_prefix=raw_key[:8],
            org__memberships__user__username=user.username,
            type__in=[MsaCredential.Type.SMTP, MsaCredential.Type.SMTP_IP],
            hold=False,
        )
        assert qs.exists()

    def test_create_with_key__returns_credential_and_raw_key(self):
        org = Organization.objects.create(slug="o")
        cred, raw_key = MsaCredential.objects.create_with_key(org=org, name="prod")
        assert cred.pk is not None
        assert cred.key_prefix == raw_key[:8]
        assert cred.org == org
        assert cred.name == "prod"


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
            (Transmission.Status.SENT, "success"),
            (Transmission.Status.FAILED, "destructive"),
            (Transmission.Status.BOUNCED, "destructive"),
            (Transmission.Status.RETRY, "outline"),
        ],
    )
    def test_status_badge_variant(self, status, expected):
        assert Transmission(status=status).status_badge_variant == expected
