import base64
from unittest.mock import patch

import dns.exception
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from abstract.mailauth import AuthResult
from domains.models import Domain
from kms.models import SigningKey
from services.email.mta.models import (
    Webhook,
    is_fbl_report,
    is_fbl_sender_authenticated,
    is_spf_pass,
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


class TestIsFblReport:
    def test_is_fbl_report__is_platform_reporting_address_from_allowed_sender(
        self, settings
    ):
        settings.RELAY_PLATFORM_DOMAIN = "relays.test"
        settings.RELAY_FBL_SENDERS = ["gmail.com"]
        assert is_fbl_report("feedback@gmail.com", "fbl@relays.test") is True

    def test_is_fbl_report__rejects_all_senders_when_allowlist_is_empty(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relays.test"
        settings.RELAY_FBL_SENDERS = []
        assert is_fbl_report("feedback@gmail.com", "fbl@relays.test") is False

    def test_is_fbl_report__matches_allowed_sender_email(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relays.test"
        settings.RELAY_FBL_SENDERS = ["feedback-loops@yahoo.com"]
        assert is_fbl_report("feedback-loops@yahoo.com", "fbl@relays.test") is True

    def test_is_fbl_report__rejects_unknown_sender(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relays.test"
        settings.RELAY_FBL_SENDERS = ["gmail.com"]
        assert is_fbl_report("forged@example.org", "fbl@relays.test") is False

    def test_is_fbl_report__rejects_customer_reporting_address(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relays.test"
        settings.RELAY_FBL_SENDERS = ["gmail.com"]
        assert is_fbl_report("feedback@gmail.com", "fbl@acme.com") is False

    def test_is_fbl_report__is_case_insensitive(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relays.test"
        settings.RELAY_FBL_SENDERS = ["gmail.com"]
        assert is_fbl_report("Feedback@GMAIL.com", "FBL@Relays.Test.") is True


class TestIsSpfPass:
    def test_is_spf_pass__passes_when_sender_is_authorized(self):
        with patch("services.email.mta.models.spf.check2", return_value=("pass", "")):
            assert is_spf_pass("feedback@gmail.com", "127.0.0.1") is True

    def test_is_spf_pass__rejects_non_pass_result(self):
        with patch(
            "services.email.mta.models.spf.check2", return_value=("softfail", "")
        ):
            assert is_spf_pass("feedback@gmail.com", "127.0.0.1") is False

    def test_is_spf_pass__rejects_empty_client_ip_without_lookup(self):
        with patch("services.email.mta.models.spf.check2") as check2:
            assert is_spf_pass("feedback@gmail.com", "") is False
        check2.assert_not_called()

    def test_is_spf_pass__rejects_on_dns_exception(self):
        with patch(
            "services.email.mta.models.spf.check2",
            side_effect=dns.exception.DNSException("resolver unavailable"),
        ):
            assert is_spf_pass("feedback@gmail.com", "192.0.2.1") is False

    def test_is_spf_pass__rejects_invalid_client_ip(self):
        assert is_spf_pass("feedback@gmail.com", "not-an-ip") is False


class TestIsFblSenderAuthenticated:
    def test_is_fbl_sender_authenticated__spf_pass_accepts_without_dkim(self):
        with (
            patch("services.email.mta.models.is_spf_pass", return_value=True),
            patch("services.email.mta.models.DmarcEvaluation") as evaluation,
        ):
            assert (
                is_fbl_sender_authenticated("feedback@gmail.com", "192.0.2.1", b"")
                is True
            )
        evaluation.verify_dkim.assert_not_called()

    def test_is_fbl_sender_authenticated__accepts_dkim_from_envelope_domain(self):
        with patch(
            "services.email.mta.models.DmarcEvaluation.verify_dkim",
            return_value=(AuthResult.PASS, "gmail.com"),
        ):
            assert is_fbl_sender_authenticated("feedback@gmail.com", "", b"") is True

    def test_is_fbl_sender_authenticated__accepts_dkim_from_listed_sender(
        self, settings
    ):
        settings.RELAY_FBL_SENDERS = ["fbl.partner.example"]
        with patch(
            "services.email.mta.models.DmarcEvaluation.verify_dkim",
            return_value=(AuthResult.PASS, "fbl.partner.example"),
        ):
            assert is_fbl_sender_authenticated("abuse@other.example", "", b"") is True

    def test_is_fbl_sender_authenticated__rejects_dkim_from_unlisted_domain(self):
        with patch(
            "services.email.mta.models.DmarcEvaluation.verify_dkim",
            return_value=(AuthResult.PASS, "evil.example"),
        ):
            assert is_fbl_sender_authenticated("feedback@gmail.com", "", b"") is False

    def test_is_fbl_sender_authenticated__rejects_failed_dkim(self):
        with patch(
            "services.email.mta.models.DmarcEvaluation.verify_dkim",
            return_value=(AuthResult.FAIL, ""),
        ):
            assert is_fbl_sender_authenticated("feedback@gmail.com", "", b"") is False

    def test_is_fbl_sender_authenticated__matches_dkim_domain_case_insensitively(self):
        with patch(
            "services.email.mta.models.DmarcEvaluation.verify_dkim",
            return_value=(AuthResult.PASS, "GMAIL.com"),
        ):
            assert is_fbl_sender_authenticated("feedback@gmail.com", "", b"") is True
