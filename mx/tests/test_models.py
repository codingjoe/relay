import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.conf import settings

from kms.models import SigningKey
from mx.models import Webhook


@pytest.fixture
def webhook(org):
    signing_key = SigningKey.generate("ed25519")
    return Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="My hook",
        address_pattern="*@app.acme.com",
        signing_key=signing_key,
    )


class TestWebhookStr:
    def test_str__shows_org_and_name(self, org, webhook):
        assert str(org) in str(webhook)
        assert "My hook" in str(webhook)

    def test_str__falls_back_to_url_when_no_name(self, org):
        signing_key = SigningKey.generate("ed25519")
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            name="",
            address_pattern="*@app.acme.com",
            signing_key=signing_key,
        )
        assert "example.com/hook" in str(webhook)


class TestReceivingDomainName:
    def test_receiving_domain_name__strips_user_part(self, webhook):
        assert webhook.receiving_domain_name == "app.acme.com"

    def test_receiving_domain_name__works_without_user_part(self, org):
        signing_key = SigningKey.generate("ed25519")
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern="app.acme.com",
            signing_key=signing_key,
        )
        assert webhook.receiving_domain_name == "app.acme.com"


class TestIsFreeDomain:
    def test_is_free_domain__true_when_matches_free(self, org):
        signing_key = SigningKey.generate("ed25519")
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern=f"*@{settings.RELAY_FREE_SENDER_DOMAIN}",
            signing_key=signing_key,
        )
        assert webhook.is_free_domain is True

    def test_is_free_domain__case_insensitive(self, org):
        signing_key = SigningKey.generate("ed25519")
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern=f"*@{settings.RELAY_FREE_SENDER_DOMAIN.upper()}",
            signing_key=signing_key,
        )
        assert webhook.is_free_domain is True

    def test_is_free_domain__false_for_custom_domain(self, webhook):
        assert webhook.is_free_domain is False


class TestMatches:
    def test_matches__exact(self, org):
        signing_key = SigningKey.generate("ed25519")
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern="support@acme.com",
            signing_key=signing_key,
        )
        assert webhook.matches("support@acme.com") is True
        assert webhook.matches("info@acme.com") is False

    def test_matches__wildcard_prefix(self, webhook):
        assert webhook.matches("alice@app.acme.com") is True
        assert webhook.matches("bob@app.acme.com") is True

    def test_matches__rejects_other_domains(self, webhook):
        assert webhook.matches("alice@other.com") is False

    def test_matches__case_insensitive(self, webhook):
        assert webhook.matches("Alice@APP.ACME.COM") is True


class TestMxRecord:
    def test_mx_record__empty_for_free_domain(self, org):
        signing_key = SigningKey.generate("ed25519")
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern=f"*@{settings.RELAY_FREE_SENDER_DOMAIN}",
            signing_key=signing_key,
        )
        assert webhook.mx_record == ""

    def test_mx_record__shows_mx_record_for_custom_domain(self, webhook):
        assert webhook.mx_record == "MX app.acme.com → mail.relay.app.acme.com"


class TestMxTarget:
    def test_mx_target__uses_sender_subdomain_prefix_for_custom_domain(self, webhook):
        assert webhook.mx_target == "mail.relay.app.acme.com"


class TestPublicKeySerialized:
    def test_public_key_serialized__starts_with_whpk(self, webhook):
        assert webhook.public_key_serialized.startswith("whpk_")

    def test_public_key_serialized__decodes_to_valid_ed25519_public_key(self, webhook):
        decoded = base64.b64decode(webhook.public_key_serialized.removeprefix("whpk_"))
        assert len(decoded) == 32  # Ed25519 raw public key is 32 bytes
        Ed25519PublicKey.from_public_bytes(decoded)


class TestSign:
    def test_sign__produces_standard_webhooks_signature(self, webhook):
        signature = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        assert signature.startswith("v1a,")

    def test_sign__decodes_to_64_byte_ed25519_signature(self, webhook):
        signature = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        decoded = base64.b64decode(signature.removeprefix("v1a,"))
        assert len(decoded) == 64  # Ed25519 signatures are 64 bytes

    def test_sign__is_deterministic_for_same_inputs(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        assert sig1 == sig2

    def test_sign__differs_for_different_payloads(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_abc", 1234567890, b'{"foo":"baz"}')
        assert sig1 != sig2

    def test_sign__differs_for_different_msg_ids(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_def", 1234567890, b'{"foo":"bar"}')
        assert sig1 != sig2

    def test_sign__differs_for_different_timestamps(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_abc", 1234567891, b'{"foo":"bar"}')
        assert sig1 != sig2

    def test_sign__verifiable_with_public_key(self, webhook):
        """The signature must verify using the webhook's public key."""
        msg_id = "msg_abc"
        timestamp = 1234567890
        payload = b'{"foo":"bar"}'
        signature = webhook.sign(msg_id, timestamp, payload)
        signed_content = f"{msg_id}.{timestamp}.".encode() + payload
        sig_bytes = base64.b64decode(signature.removeprefix("v1a,"))
        public_key = Ed25519PublicKey.from_public_bytes(
            webhook.signing_key.public_bytes_raw()
        )
        public_key.verify(sig_bytes, signed_content)
