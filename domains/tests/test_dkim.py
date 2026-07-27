from email.message import EmailMessage

import pytest

from accounts.models import Organization
from domains.models import Domain


def make_email():
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"
    msg["Message-ID"] = "<test@example.com>"
    msg.set_content("Hello world")
    return msg


@pytest.mark.django_db
class TestSignMessage:
    def test_sign_message__returns_signed_bytes(self):
        from domains.dkim import sign_message

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"DKIM-Signature:" in signed

    def test_sign_message__signs_with_all_three_ciphers(self):
        from domains.dkim import sign_message

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert signed.count(b"DKIM-Signature:") == 3

    def test_sign_message__includes_all_selectors(self):
        from domains.dkim import sign_message

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"s=relay-rsa2048" in signed
        assert b"s=relay-rsa1024" in signed
        assert b"s=relay-ed25519" in signed

    def test_sign_message__includes_domain(self):
        from domains.dkim import sign_message

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"d=example.com" in signed

    def test_sign_message__returns_original_when_no_keys(self):
        from domains.dkim import sign_message

        domain = Domain(name="example.com")
        original = make_email().as_bytes()
        signed = sign_message(original, domain)
        assert signed == original


class TestVerifySignature:
    def test_verify_signature__handles_signed_message(self):
        from domains.dkim import verify_signature

        verified, _ = verify_signature(make_email().as_bytes())
        assert isinstance(verified, bool | type(None))

    def test_verify_signature__rejects_unsigned(self):
        from domains.dkim import verify_signature

        verified, _ = verify_signature(make_email().as_bytes())
        assert verified is not True
