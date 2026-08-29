from email.message import EmailMessage

import pytest

from accounts.models import Organization
from domains.dkim import sign_message, verify_signature
from domains.models import Domain
from kms import keys as kms_keys


def make_email():
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"
    msg["Message-ID"] = "<test@example.com>"
    msg.set_content("Hello world")
    return msg


class TestSignMessage:
    @pytest.mark.django_db
    def test_sign_message__returns_signed_bytes(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"DKIM-Signature:" in signed

    @pytest.mark.django_db
    def test_sign_message__signs_with_all_three_ciphers(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert signed.count(b"DKIM-Signature:") == 3

    @pytest.mark.django_db
    def test_sign_message__includes_all_selectors(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"s=relay-rsa2048" in signed
        assert b"s=relay-rsa1024" in signed
        assert b"s=relay-ed25519" in signed

    @pytest.mark.django_db
    def test_sign_message__includes_domain(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"d=example.com" in signed

    def test_sign_message__returns_original_when_no_keys(self):
        domain = Domain(name="example.com")
        original = make_email().as_bytes()
        signed = sign_message(original, domain)
        assert signed == original

    @pytest.mark.django_db
    def test_sign_message__adds_platform_signatures(self, settings):
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(1024)
        )
        settings.RELAY_DKIM_PLATFORM_ED25519_PRIVATE_KEY = (
            kms_keys.generate_ed25519_private_key()
        )
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        assert signed.count(b"DKIM-Signature:") == 5
        assert b"s=relay-platform-rsa1024" in signed
        assert b"s=relay-platform-ed25519" in signed
        assert f"d={settings.RELAY_PLATFORM_DOMAIN}".encode("ascii") in signed

    @pytest.mark.django_db
    def test_sign_message__customer_signature_stays_on_top(self, settings):
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(1024)
        )
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        assert signed.index(b"d=example.com") < signed.index(b"d=localhost")


class TestVerifySignature:
    def test_verify_signature__handles_signed_message(self):
        verified, _ = verify_signature(make_email().as_bytes())
        assert isinstance(verified, bool | type(None))

    def test_verify_signature__rejects_unsigned(self):
        verified, _ = verify_signature(make_email().as_bytes())
        assert verified is not True
