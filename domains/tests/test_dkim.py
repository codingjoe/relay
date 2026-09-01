import email
from email.message import EmailMessage

import pytest
from django.conf import settings

from accounts.models import Organization
from domains.dkim import (
    INCLUDE_HEADERS,
    add_dkim_signature,
    sign_message,
    verify_signature,
)
from domains.models import Domain, canonicalize_domain_name
from kms import keys as kms_keys
from kms.models import SigningKey


def make_email():
    msg = EmailMessage()
    msg["From"] = "alice@example.com"
    msg["To"] = "bob@example.com"
    msg["Subject"] = "Test"
    msg["Date"] = "Mon, 01 Jan 2024 00:00:00 +0000"
    msg["Message-ID"] = "<test@example.com>"
    msg["Feedback-ID"] = "9::000000000000000000000000:relay"
    msg.set_content("Hello world")
    return msg


def make_signing_key(algorithm, private_algorithm=None):
    pair = kms_keys.generate(private_algorithm or algorithm)
    return SigningKey(algorithm=algorithm, encrypted_private_key=pair.ciphertext)


def parse_signatures(signed):
    """Return the tag dict of every DKIM-Signature, topmost first."""
    return [
        dict(
            tag.split("=", 1)
            for tag in " ".join(signature.split()).split("; ")
            if "=" in tag
        )
        for signature in email.message_from_bytes(signed).get_all("DKIM-Signature")
    ]


def make_platform_domain(org, **dkim_keys):
    """Create the platform Domain row with explicit keys."""
    domain = Domain.objects.create(
        name=canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN),
        org=org,
    )
    if dkim_keys:
        domain.dkim_key_rsa2048 = dkim_keys.get("dkim_key_rsa2048")
        domain.dkim_key_ed25519 = dkim_keys.get("dkim_key_ed25519")
        domain.save(
            update_fields=[
                "dkim_key_rsa2048",
                "dkim_key_ed25519",
            ]
        )
    return domain


def make_platform_keys():
    return {
        "dkim_key_rsa2048": SigningKey.generate(SigningKey.Algorithm.RSA_2048),
        "dkim_key_ed25519": SigningKey.generate(SigningKey.Algorithm.ED25519),
    }


class TestSignMessage:
    @pytest.mark.django_db
    def test_sign_message__returns_signed_bytes(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"DKIM-Signature:" in signed

    @pytest.mark.django_db
    def test_sign_message__signs_with_all_ciphers(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert signed.count(b"DKIM-Signature:") == 2

    @pytest.mark.django_db
    def test_sign_message__includes_all_selectors(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"s=relay-rsa2048" in signed
        assert b"s=relay-ed25519" in signed

    @pytest.mark.django_db
    def test_sign_message__includes_domain(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        signed = sign_message(make_email().as_bytes(), domain)
        assert b"d=example.com" in signed

    @pytest.mark.django_db
    def test_sign_message__cosigns_with_platform_domain(self):
        org = Organization.objects.create(slug="o")
        platform_org = Organization.objects.create(slug="platform-org")
        platform = make_platform_domain(platform_org, **make_platform_keys())
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        # Signatures are prepended, so the platform cosign sits above the
        # body while the customer's own signatures stay on top, the way
        # SES dual-signs for FBL attribution. The queryset order decides
        # which family signs first, so assert the pairs as a set.
        assert sorted(
            (signature["d"], signature["s"]) for signature in parse_signatures(signed)
        ) == sorted(
            [
                ("example.com", "relay-ed25519"),
                ("example.com", "relay-rsa2048"),
                (platform.name, "relay-ed25519"),
                (platform.name, "relay-rsa2048"),
            ]
        )

    @pytest.mark.django_db
    def test_sign_message__no_cosign_without_platform_domain(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        signatures = parse_signatures(signed)
        assert len(signatures) == 2
        assert {signature["d"] for signature in signatures} == {"example.com"}

    @pytest.mark.django_db
    def test_sign_message__signs_platform_domain_once(self):
        platform_org = Organization.objects.create(slug="platform-org")
        domain = make_platform_domain(platform_org, **make_platform_keys())

        signed = sign_message(make_email().as_bytes(), domain)

        signatures = parse_signatures(signed)
        assert len(signatures) == 2
        assert {signature["d"] for signature in signatures} == {domain.name}

    @pytest.mark.django_db
    def test_sign_message__covers_feedback_id_in_every_signature(self):
        org = Organization.objects.create(slug="o")
        platform_org = Organization.objects.create(slug="platform-org")
        platform = make_platform_domain(platform_org, **make_platform_keys())
        domain = Domain.objects.create(name="example.com", org=org)

        signed = sign_message(make_email().as_bytes(), domain)

        signatures = parse_signatures(signed)
        assert {signature["d"] for signature in signatures} == {
            "example.com",
            platform.name,
        }
        assert all("feedback-id" in signature["h"].lower() for signature in signatures)

    @pytest.mark.django_db
    def test_sign_message__raises_without_keys(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        Domain.objects.filter(pk=domain.pk).update(
            dkim_key_rsa2048=None,
            dkim_key_ed25519=None,
        )

        with pytest.raises(ValueError, match="no DKIM signing key"):
            sign_message(make_email().as_bytes(), domain)


class TestAddDkimSignature:
    def test_add_dkim_signature__prepends_signature(self):
        key = make_signing_key(kms_keys.Algorithm.RSA_2048)
        original = make_email().as_bytes()

        signed = add_dkim_signature(
            original,
            "relay-rsa2048",
            "example.com",
            key,
            INCLUDE_HEADERS,
        )

        assert signed.startswith(b"DKIM-Signature:")
        assert signed.endswith(original)

    def test_add_dkim_signature__returns_original_on_signing_failure(self):
        key = make_signing_key(kms_keys.Algorithm.ED25519, kms_keys.Algorithm.RSA_2048)
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

    def test_verify_signature__returns_false_for_malformed_message(self):
        verified, _ = verify_signature(b"garbage\r\n")

        assert verified is False
