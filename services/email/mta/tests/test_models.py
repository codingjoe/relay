import base64
import hashlib
import hmac

import pytest

from domains.models import Domain
from services.email.mta.models import TlsFailure, Webhook, WebhookDelivery


@pytest.fixture
def webhook(org):
    domain = Domain.objects.create(name="app.acme.com", org=org)
    return Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="My hook",
        address_pattern="*@app.acme.com",
        domain=domain,
    )


class TestWebhookStr:
    @pytest.mark.django_db
    def test_str__shows_org_and_name(self, org, webhook):
        assert str(org) in str(webhook)
        assert "My hook" in str(webhook)

    @pytest.mark.django_db
    def test_str__falls_back_to_url_when_no_name(self, org):
        domain = Domain.objects.create(name="app.acme.com", org=org)
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            name="",
            address_pattern="*@app.acme.com",
            domain=domain,
        )
        assert "example.com/hook" in str(webhook)


class TestMatches:
    @pytest.mark.django_db
    def test_matches__exact(self, org):
        domain = Domain.objects.create(name="acme.com", org=org)
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern="support@acme.com",
            domain=domain,
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
        domain = Domain.objects.get(org=org, is_managed=True)
        webhook = Webhook.objects.create(
            org=org,
            url="https://example.com/hook",
            address_pattern=f"*@{domain.name}",
            domain=domain,
        )

        assert webhook.mx_record == ""


class TestSigningSecret:
    @pytest.mark.django_db
    def test_signing_secret__starts_with_whsec(self, webhook):
        assert webhook.signing_secret.startswith("whsec_")

    @pytest.mark.django_db
    def test_signing_secret__decodes_to_32_bytes(self, webhook):
        decoded = base64.b64decode(webhook.signing_secret.removeprefix("whsec_"))
        assert len(decoded) == 32

    @pytest.mark.django_db
    def test_signing_secret__is_unique_per_webhook(self, org, webhook):
        domain = Domain.objects.create(name="other.acme.com", org=org)
        other = Webhook.objects.create(
            org=org,
            url="https://example.com/other",
            address_pattern="*@other.acme.com",
            domain=domain,
        )
        assert other.signing_secret != webhook.signing_secret

    @pytest.mark.django_db
    def test_encrypted_signing_secret__does_not_contain_plaintext(self, webhook):
        assert webhook.signing_secret not in webhook.encrypted_signing_secret


class TestSign:
    @pytest.mark.django_db
    def test_sign__produces_standard_webhooks_signature(self, webhook):
        signature = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        assert signature.startswith("v1,")

    @pytest.mark.django_db
    def test_sign__decodes_to_32_byte_hmac(self, webhook):
        signature = webhook.sign("msg_abc", 1234567890, b'{"foo":"bar"}')
        decoded = base64.b64decode(signature.removeprefix("v1,"))
        assert len(decoded) == 32  # HMAC-SHA256 produces 32 bytes

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
    def test_sign__verifiable_with_signing_secret(self, webhook):
        """The signature must verify the Standard Webhooks signature scheme."""
        msg_id = "msg_abc"
        timestamp = 1234567890
        payload = b'{"foo":"bar"}'
        signature = webhook.sign(msg_id, timestamp, payload)
        signed_content = f"{msg_id}.{timestamp}.".encode() + payload
        secret = base64.b64decode(webhook.signing_secret.removeprefix("whsec_"))
        expected = hmac.new(secret, signed_content, hashlib.sha256).digest()
        sig_bytes = base64.b64decode(signature.removeprefix("v1,"))
        assert hmac.compare_digest(sig_bytes, expected)


class TestWebhookDeliveryRepr:
    def test_repr__returns_pk(self):
        assert repr(WebhookDelivery(pk=1)) == "<WebhookDelivery 1>"


class TestTlsFailureRepr:
    def test_repr__returns_pk(self):
        assert repr(TlsFailure(pk=1)) == "<TlsFailure 1>"


class TestTlsFailureRelaySender:
    def test_is_relay_sender__true_for_configured_address(self, settings):
        settings.SMTP_SOURCE_IPS = ["10.0.0.9"]
        failure = TlsFailure(sending_mta_ip_address="10.0.0.9")
        assert failure.is_relay_sender

    def test_is_relay_sender__false_for_other_address(self, settings):
        settings.SMTP_SOURCE_IPS = ["10.0.0.9"]
        settings.DNS_SMTP_IPS = []
        failure = TlsFailure(sending_mta_ip_address="10.0.0.10")
        assert not failure.is_relay_sender
