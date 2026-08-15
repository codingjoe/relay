import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.db import IntegrityError

from domains.models import Domain
from kms import envelope
from kms.models import SigningKey
from services.email.mx.models import (
    IncomingMessage,
    SealedFileKey,
    Webhook,
    WebhookEncryptionKey,
)


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

    @pytest.mark.django_db
    def test_mx_record__empty_for_managed_domain(self, org):
        signing_key = SigningKey.generate("ed25519")
        domain = Domain.objects.get(org=org, is_managed=True)
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern=f"*@{domain.name}",
            domain=domain,
            signing_key=signing_key,
        )

        assert webhook.mx_record == ""


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


@pytest.fixture
def incoming_message(org):
    domain = Domain.objects.get(org=org, is_managed=True)
    return IncomingMessage.objects.create(
        org=org,
        domain=domain,
        receiving_domain="example.com",
        mail_from="alice@example.com",
        rcpt_to="bob@example.com",
        subject="Hello",
        message_id="<abc@example.com>",
    )


def _make_webhook_encryption_key(webhook):
    """Create a WebhookEncryptionKey with a fresh X25519 keypair."""
    pair = envelope.generate_x25519_keypair()
    return WebhookEncryptionKey.objects.create(
        webhook=webhook,
        public_key=envelope.encode_key(pair.public_key),
        key_id=envelope.key_fingerprint(pair.public_key),
    )


class TestWebhookEncryptionKeyCreate:
    @pytest.mark.django_db
    def test_create__persists_fields(self, webhook):
        pair = envelope.generate_x25519_keypair()
        public_key = envelope.encode_key(pair.public_key)
        key_id = envelope.key_fingerprint(pair.public_key)
        key = WebhookEncryptionKey.objects.create(
            webhook=webhook,
            public_key=public_key,
            key_id=key_id,
        )
        key.refresh_from_db()
        assert key.webhook == webhook
        assert key.public_key == public_key
        assert key.key_id == key_id

    @pytest.mark.django_db
    def test_str__shows_webhook_and_key_id(self, webhook):
        pair = envelope.generate_x25519_keypair()
        key_id = envelope.key_fingerprint(pair.public_key)
        key = WebhookEncryptionKey.objects.create(
            webhook=webhook,
            public_key=envelope.encode_key(pair.public_key),
            key_id=key_id,
        )
        assert str(key) == f"{webhook} / {key_id}"


class TestWebhookEncryptionKeyConstraints:
    @pytest.mark.django_db
    def test_one_to_one__only_one_per_webhook(self, webhook):
        _make_webhook_encryption_key(webhook)
        with pytest.raises(IntegrityError):
            _make_webhook_encryption_key(webhook)


class TestSealedFileKeyCreate:
    @pytest.mark.django_db
    def test_create__persists_fields(self, webhook, incoming_message):
        webhook_key = _make_webhook_encryption_key(webhook)
        file_key = envelope.generate_file_key()
        sealed = envelope.seal_file_key(
            file_key, envelope.decode_key(webhook_key.public_key)
        )
        sfk = SealedFileKey.objects.create(
            message=incoming_message,
            webhook=webhook,
            sealed_key=envelope.encode_key(sealed),
        )
        sfk.refresh_from_db()
        assert sfk.message == incoming_message
        assert sfk.webhook == webhook
        assert sfk.sealed_key == envelope.encode_key(sealed)

    @pytest.mark.django_db
    def test_str__shows_message_and_webhook(self, webhook, incoming_message):
        sfk = SealedFileKey.objects.create(
            message=incoming_message,
            webhook=webhook,
            sealed_key="sealed-key",
        )
        assert str(sfk) == f"{incoming_message} → {webhook}"


class TestSealedFileKeyConstraints:
    @pytest.mark.django_db
    def test_unique__message_and_webhook(self, webhook, incoming_message):
        SealedFileKey.objects.create(
            message=incoming_message,
            webhook=webhook,
            sealed_key="sealed1",
        )
        with pytest.raises(IntegrityError):
            SealedFileKey.objects.create(
                message=incoming_message,
                webhook=webhook,
                sealed_key="sealed2",
            )
