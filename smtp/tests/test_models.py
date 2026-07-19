import pytest
from django.contrib.auth.models import User

from accounts.models import Organization
from smtp.models import OutgoingMessage, SmtpCredential, Transmission


@pytest.mark.django_db
class TestOutgoingMessageStr:
    def test_str__shows_from_to_and_status(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="O")
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
            subject="Hello",
            status=OutgoingMessage.Status.PENDING,
        )
        assert "alice@example.com" in str(msg)
        assert "bob@example.com" in str(msg)
        assert "pending" in str(msg)


@pytest.mark.django_db
class TestOutgoingMessageDefaults:
    def test_default_status__pending(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="O")
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
        )
        assert msg.status == OutgoingMessage.Status.PENDING

    def test_default_received_with_ssl__false(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="O")
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
        )
        assert msg.received_with_ssl is False


@pytest.mark.django_db
class TestTransmissionStr:
    def test_str__includes_message_and_status(self):
        user = User.objects.create_user(username="alice", email="a@example.com")
        org = Organization.objects.create(name="O")
        msg = OutgoingMessage.objects.create(
            sender=user,
            org=org,
            rcpt_to="bob@example.com",
            mail_from="alice@example.com",
        )
        t = Transmission.objects.create(message=msg, status=Transmission.Status.SENT)
        assert str(msg) in str(t)
        assert "sent" in str(t)


@pytest.mark.django_db
class TestSmtpCredential:
    def test_type__defaults_to_smtp(self):
        org = Organization.objects.create(name="O")
        cred, _ = SmtpCredential.objects.create_with_key(org=org)
        assert cred.type == SmtpCredential.Type.SMTP

    def test_inherits_credential__has_key_fields(self):
        org = Organization.objects.create(name="O")
        cred, raw_key = SmtpCredential.objects.create_with_key(org=org, name="prod")
        assert cred.key_hash
        assert cred.key_prefix == raw_key[:8]
        assert cred.salt == "smtp.models.SmtpCredential"
        assert cred.org == org

    def test_str__shows_org_and_name(self):
        org = Organization.objects.create(name="Acme")
        cred, _ = SmtpCredential.objects.create_with_key(org=org, name="prod")
        assert "Acme" in str(cred)
        assert "prod" in str(cred)
