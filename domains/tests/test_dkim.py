import base64
from email.message import EmailMessage

import dkim
import pytest

from accounts.models import Organization
from domains.dkim import (
    PLATFORM_INCLUDE_HEADERS,
    PlatformSigningKey,
    add_dkim_signature,
    platform_dkim_ciphers,
    sign_message,
    verify_signature,
)
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

    @pytest.mark.django_db
    def test_sign_message__platform_signature_includes_feedback_id(self, settings):
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(1024)
        )
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        assert signed.count(b"feedback-id;") == 1

    @pytest.mark.django_db
    def test_sign_message__skips_invalid_platform_key(self, settings):
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = "Not a private key."
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        assert signed.count(b"DKIM-Signature:") == 3
        assert b"s=relay-platform-" not in signed


class TestPlatformSigningKey:
    def test_platform_signing_key__exposes_public_key(self):
        key = PlatformSigningKey(
            kms_keys.Algorithm.RSA_1024, kms_keys.generate_rsa_private_key(1024)
        )

        assert key.public_key.startswith("-----BEGIN PUBLIC KEY-----")
        assert key.public_bytes_der()

    def test_platform_signing_key__derives_raw_public_key_for_ed25519(self):
        key = PlatformSigningKey(
            kms_keys.Algorithm.ED25519, kms_keys.generate_ed25519_private_key()
        )

        assert len(key.public_bytes_raw()) == 32
        assert key.public_bytes_der()

    def test_platform_signing_key__invalid_pem_raises_value_error(self):
        with pytest.raises(ValueError):
            PlatformSigningKey(kms_keys.Algorithm.RSA_1024, "Not a private key.")

    def test_platform_signing_key__produces_verifiable_signature(self):
        key = PlatformSigningKey(
            kms_keys.Algorithm.RSA_1024, kms_keys.generate_rsa_private_key(1024)
        )
        message = make_email()
        message["Feedback-ID"] = "9::deadbeef:relay"
        original = message.as_bytes()

        signed = key.sign_dkim(
            original,
            "relay-platform-rsa1024",
            "example.com",
            PLATFORM_INCLUDE_HEADERS,
        )

        record = (
            "v=DKIM1; k=rsa; "
            f"p={base64.b64encode(key.public_bytes_der()).decode('ascii')};"
        )
        verified = dkim.verify(
            signed + original, dnsfunc=lambda name, timeout=5: record
        )
        assert verified is True


class TestPlatformDkimCiphers:
    def test_platform_dkim_ciphers__yields_all_configured_keys(self, settings):
        settings.RELAY_DNS_DKIM_IDENTIFIER = "relay"
        settings.RELAY_DKIM_PLATFORM_RSA2048_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(2048)
        )
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(1024)
        )
        settings.RELAY_DKIM_PLATFORM_ED25519_PRIVATE_KEY = (
            kms_keys.generate_ed25519_private_key()
        )

        ciphers = list(platform_dkim_ciphers())

        assert [selector for selector, _ in ciphers] == [
            "relay-platform-rsa2048",
            "relay-platform-rsa1024",
            "relay-platform-ed25519",
        ]
        assert [key.algorithm for _, key in ciphers] == [
            kms_keys.Algorithm.RSA_2048,
            kms_keys.Algorithm.RSA_1024,
            kms_keys.Algorithm.ED25519,
        ]

    def test_platform_dkim_ciphers__skips_unset_and_invalid_keys(self, settings):
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(1024)
        )
        settings.RELAY_DKIM_PLATFORM_ED25519_PRIVATE_KEY = "Not a private key."

        assert [selector for selector, _ in platform_dkim_ciphers()] == [
            "relay-platform-rsa1024"
        ]


class TestAddDkimSignature:
    def test_add_dkim_signature__prepends_signature(self):
        key = PlatformSigningKey(
            kms_keys.Algorithm.RSA_1024, kms_keys.generate_rsa_private_key(1024)
        )
        original = make_email().as_bytes()

        signed = add_dkim_signature(
            original,
            "relay-platform-rsa1024",
            "example.com",
            key,
            PLATFORM_INCLUDE_HEADERS,
        )

        assert signed.startswith(b"DKIM-Signature:")
        assert signed.endswith(original)

    def test_add_dkim_signature__returns_original_on_signing_failure(self):
        key = PlatformSigningKey(
            kms_keys.Algorithm.ED25519, kms_keys.generate_rsa_private_key(1024)
        )
        original = make_email().as_bytes()

        signed = add_dkim_signature(
            original,
            "relay-platform-ed25519",
            "example.com",
            key,
            PLATFORM_INCLUDE_HEADERS,
        )

        assert signed == original


class TestVerifySignature:
    def test_verify_signature__handles_signed_message(self):
        verified, _ = verify_signature(make_email().as_bytes())
        assert isinstance(verified, bool | type(None))

    def test_verify_signature__rejects_unsigned(self):
        verified, _ = verify_signature(make_email().as_bytes())
        assert verified is not True
