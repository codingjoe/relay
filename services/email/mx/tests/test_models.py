import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from domains.models import Domain
from kms.models import SigningKey
from services.email.mx.models import Webhook


@pytest.fixture
def webhook(org):
    signing_key = SigningKey.generate("ed25519")
    domain = Domain.objects.create(name="app.acme.com", org=org)
    return Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="My hook",
        address_pattern="*@app.acme.com",
        domain=domain,
        signing_key=signing_key,
    )


class TestWebhookStr:
    @pytest.mark.django_db
    def test_str__shows_org_and_name(self, org, webhook):
        assert str(org) in str(webhook)
        assert "My hook" in str(webhook)

    @pytest.mark.django_db
    def test_str__falls_back_to_url_when_no_name(self, org):
        signing_key = SigningKey.generate("ed25519")
        domain = Domain.objects.create(name="app.acme.com", org=org)
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            name="",
            address_pattern="*@app.acme.com",
            domain=domain,
            signing_key=signing_key,
        )
        assert "example.com/hook" in str(webhook)


class TestMatches:
    @pytest.mark.django_db
    def test_matches__exact(self, org):
        signing_key = SigningKey.generate("ed25519")
        domain = Domain.objects.create(name="acme.com", org=org)
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern="support@acme.com",
            domain=domain,
            signing_key=signing_key,
        )
        assert webhook.matches("support@acme.com") is True
        assert webhook.matches("info@acme.com") is False

    @pytest.mark.django_db
    def test_matches__wildcard_prefix(self, webhook):
        assert webhook.matches("alice@app.acme.com") is True
        assert webhook.matches("bob@app.acme.com") is True

    @pytest.mark.django_db
    def test_matches__rejects_other_domains(self, webhook):
        assert webhook.matches("alice@other.com") is False

    @pytest.mark.django_db
    def test_matches__case_insensitive(self, webhook):
        assert webhook.matches("Alice@APP.ACME.COM") is True


class TestMxRecord:
    @pytest.mark.django_db
    def test_mx_record__shows_mx_record_for_custom_domain(self, webhook):
        assert webhook.mx_record == "MX app.acme.com → mail.relay.app.acme.com"


class TestPublicKeySerialized:
    @pytest.mark.django_db
    def test_public_key_serialized__starts_with_whpk(self, webhook):
        assert webhook.public_key_serialized.startswith("whpk_")

    @pytest.mark.django_db
    def test_public_key_serialized__decodes_to_valid_ed25519_public_key(self, webhook):
        decoded = base64.b64decode(webhook.public_key_serialized.removeprefix("whpk_"))
        assert len(decoded) == 32  # Ed25519 raw public key is 32 bytes
        Ed25519PublicKey.from_public_bytes(decoded)


class TestSign:
    @pytest.mark.django_db
    def test_sign__produces_standard_webhooks_signature(self, webhook):
        signature = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        assert signature.startswith("v1a,")

    @pytest.mark.django_db
    def test_sign__decodes_to_64_byte_ed25519_signature(self, webhook):
        signature = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        decoded = base64.b64decode(signature.removeprefix("v1a,"))
        assert len(decoded) == 64  # Ed25519 signatures are 64 bytes

    @pytest.mark.django_db
    def test_sign__is_deterministic_for_same_inputs(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        assert sig1 == sig2

    @pytest.mark.django_db
    def test_sign__differs_for_different_payloads(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_abc", 1234567890, b'{"foo":"baz"}')
        assert sig1 != sig2

    @pytest.mark.django_db
    def test_sign__differs_for_different_msg_ids(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_def", 1234567890, b'{"foo":"bar"}')
        assert sig1 != sig2

    @pytest.mark.django_db
    def test_sign__differs_for_different_timestamps(self, webhook):
        sig1 = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        sig2 = webhook.sign("msg_abc", 1234567891, b'{"foo":"bar"}')
        assert sig1 != sig2

    @pytest.mark.django_db
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
