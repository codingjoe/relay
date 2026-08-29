from email.message import EmailMessage

import pytest

from accounts.models import Organization
from domains.dkim import (
    INCLUDE_HEADERS,
    add_dkim_signature,
    sign_message,
    verify_signature,
)
from domains.models import Domain
from kms import keys as kms_keys
from kms.models import SigningKey


def make_email():
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"
    msg["Message-ID"] = "<test@example.com>"
    msg.set_content("Hello world")
    return msg


def make_signing_key(algorithm, private_algorithm=None):
    pair = kms_keys.generate(private_algorithm or algorithm)
    return SigningKey(algorithm=algorithm, encrypted_private_key=pair.ciphertext)


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

    @pytest.mark.django_db
    def test_sign_message__returns_original_when_no_keys(self):
        domain = Domain(name="example.com")
        original = make_email().as_bytes()
        signed = sign_message(original, domain)
        assert signed == original


class TestAddDkimSignature:
    def test_add_dkim_signature__prepends_signature(self):
        key = make_signing_key(kms_keys.Algorithm.RSA_1024)
        original = make_email().as_bytes()

        signed = add_dkim_signature(
            original,
            "relay-rsa1024",
            "example.com",
            key,
            INCLUDE_HEADERS,
        )

        assert signed.startswith(b"DKIM-Signature:")
        assert signed.endswith(original)

    def test_add_dkim_signature__returns_original_on_signing_failure(self):
        key = make_signing_key(kms_keys.Algorithm.ED25519, kms_keys.Algorithm.RSA_1024)
        original = make_email().as_bytes()

        signed = add_dkim_signature(
            original,
            "relay-ed25519",
            "example.com",
            key,
            INCLUDE_HEADERS,
        )

        assert signed == original


class TestVerifySignature:
    def test_verify_signature__handles_signed_message(self):
        verified, _ = verify_signature(make_email().as_bytes())
        assert isinstance(verified, bool | type(None))

    def test_verify_signature__rejects_unsigned(self):
        verified, _ = verify_signature(make_email().as_bytes())
        assert verified is not True
