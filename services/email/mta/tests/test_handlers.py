from email.message import EmailMessage
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core import mail

from domains.models import Domain
from kms import envelope
from kms.models import OrgEncryptionKey, SigningKey
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.mta.handlers import (
    MXHandler,
    process_incoming_message,
    save_encrypted_body,
    seal_file_keys_for_webhooks,
)
from services.email.mta.models import (
    IncomingMessage,
    SealedFileKey,
    TlsReport,
    Webhook,
    WebhookEncryptionKey,
)


def make_raw_email(subject="Postmaster alert"):
    msg = EmailMessage()
    msg["From"] = "external@example.org"
    msg["To"] = "postmaster@example.com"
    msg["Subject"] = subject
    msg.set_content("Something happened")
    return msg.as_bytes()


class TestProcessIncomingMessagePostmaster:
    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )
        message = await IncomingMessage.objects.aget(
            org=org,
            rcpt_to="postmaster@example.com",
        )
        assert result == "250 OK"
        assert message.domain == domain

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster_plus_addressing__creates_incoming_message(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            await process_incoming_message(
                "external@example.org",
                "postmaster+bounces@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )
        assert (
            IncomingMessage.objects.filter(
                org=org, rcpt_to="postmaster+bounces@example.com"
            ).count()
            == 1
        )

    @pytest.mark.django_db(transaction=True)
    async def test_postmaster__enqueues_notification(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            await process_incoming_message(
                "external@example.org",
                "postmaster@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )
        assert any("postmaster" in m.subject.lower() for m in mail.outbox)

    @pytest.mark.django_db(transaction=True)
    async def test_non_postmaster__does_not_notify(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        org.billing_is_active = True
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.org == org
        assert len(mail.outbox) == 0

    @pytest.mark.django_db(transaction=True)
    async def test_quarantined_status__stored_with_quarantine(self, org):
        domain = Domain.objects.create(name="example.com", org=org)
        with patch("services.email.mta.handlers.check_incoming_spam"):
            result = await process_incoming_message(
                "external@example.org",
                "info@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.QUARANTINED,
                "",
            )
        message = await IncomingMessage.objects.aget(domain=domain)
        assert result == "250 OK"
        assert message.status == IncomingMessage.Status.QUARANTINED


class TestHandleRcpt:
    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__rejects_unknown_domain(self, org):
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            "user@unknown.example",
            None,
        )

        assert result == "550 Relay not authorised for this recipient"
        assert envelope.rcpt_tos == []

    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__accepts_managed_domain(self, org):
        domain = await Domain.objects.aget(org=org, is_managed=True)
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            f"user@{domain.name}",
            None,
        )

        assert result == "250 OK"
        assert envelope.recipient_domain == domain

    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__selects_most_specific_domain(self, org):
        Domain.objects.create(name="example.com", org=org)
        child = Domain.objects.create(name="app.example.com", org=org)
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            "user@app.example.com",
            None,
        )

        assert result == "250 OK"
        assert envelope.recipient_domain == child

    @pytest.mark.django_db(transaction=True)
    async def test_handle_rcpt__rejects_ambiguous_cross_org_domain(
        self,
        org,
        write_org,
    ):
        await Domain.objects.abulk_create(
            [
                Domain(name="example.com", org=org),
                Domain(name="app.example.com", org=write_org),
            ]
        )
        envelope = SimpleNamespace(rcpt_tos=[])

        result = await MXHandler().handle_RCPT(
            None,
            None,
            envelope,
            "user@app.example.com",
            None,
        )

        assert result == "550 Relay not authorised for this recipient"
        assert envelope.rcpt_tos == []
        assert not hasattr(envelope, "recipient_domain")


class TestProcessIncomingMessageReports:
    @pytest.mark.django_db(transaction=True)
    @pytest.mark.parametrize(
        ("local_part", "report_model"),
        [
            (settings.RELAY_DMARC_REPORT_LOCAL_PART, DmarcReport),
            (settings.RELAY_TLS_REPORT_LOCAL_PART, TlsReport),
            (settings.RELAY_DMARC_RUF_LOCAL_PART, DmarcFailureReport),
        ],
    )
    async def test_report_recipient__binds_report_to_domain(
        self,
        org,
        local_part,
        report_model,
    ):
        domain = Domain.objects.create(name="example.com", org=org)

        with (
            patch("services.email.dmarc.tasks.parse_dmarc_report"),
            patch("services.email.mta.handlers.parse_tls_report"),
            patch("services.email.dmarc.tasks.parse_dmarc_failure_report"),
        ):
            result = await process_incoming_message(
                "external@example.org",
                f"{local_part}@example.com",
                make_raw_email(),
                True,
                domain,
                IncomingMessage.Status.RECEIVED,
                "",
            )

        report = await report_model.objects.aget(domain=domain)
        assert result == "250 OK"
        assert report.org == org


def make_org_encryption_key(org):
    pair = envelope.generate_x25519_keypair()
    return OrgEncryptionKey.objects.create(
        org=org,
        public_key=envelope.encode_key(pair.public_key),
        is_active=True,
    )


def make_encrypted_webhook(org, pattern):
    """Create an active webhook with an encryption key. Return both.

    The returned private key is the counterpart to the stored public key, so
    tests can unseal sealed file keys for round-trip verification.
    """
    signing_key = SigningKey.generate("ed25519")
    domain = Domain.objects.create(name=f"hook-{org.slug}.com", org=org)
    webhook = Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="",
        address_pattern=pattern,
        domain=domain,
        signing_key=signing_key,
    )
    pair = envelope.generate_x25519_keypair()
    WebhookEncryptionKey.objects.create(
        webhook=webhook,
        public_key=envelope.encode_key(pair.public_key),
        key_id=envelope.key_fingerprint(pair.public_key),
    )
    return webhook, pair.private_key


def make_plain_webhook(org, pattern):
    signing_key = SigningKey.generate("ed25519")
    domain = Domain.objects.create(name=f"plain-{org.slug}.com", org=org)
    return Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="",
        address_pattern=pattern,
        domain=domain,
        signing_key=signing_key,
    )


def make_unsaved_incoming(org):
    domain = Domain.objects.get(org=org, is_managed=True)
    return IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain=domain.name,
        mail_from="alice@example.com",
        rcpt_to="bob@example.com",
        subject="hi",
        message_id="<abc@example.com>",
    )


@pytest.mark.django_db
class TestSaveEncryptedBody:
    def test_save_encrypted_body__encrypts_when_org_has_key(self, org):
        org_key = make_org_encryption_key(org)
        plaintext = b"From: a@b\r\nSubject: secret\r\n\r\nbody"
        message = make_unsaved_incoming(org)
        file_key = save_encrypted_body(message, plaintext, org)
        assert file_key is not None
        assert message.sealed_file_key
        assert message.org_encryption_key_id == org_key.key_id
        ciphertext = message.raw_body.read()
        assert ciphertext != plaintext
        assert envelope.decrypt_body(ciphertext, file_key) == plaintext

    def test_save_encrypted_body__stores_plaintext_when_no_key(self, org):
        plaintext = b"From: a@b\r\nSubject: hi\r\n\r\nbody"
        message = make_unsaved_incoming(org)
        file_key = save_encrypted_body(message, plaintext, org)
        assert file_key is None
        assert message.sealed_file_key == ""
        assert message.raw_body.read() == plaintext


@pytest.mark.django_db
class TestSealFileKeysForWebhooks:
    def test_seal_file_keys_for_webhooks__creates_sealed_keys(self, org):
        webhook, private_key = make_encrypted_webhook(org, pattern="*@example.com")
        message = make_unsaved_incoming(org)
        message.rcpt_to = "bob@example.com"
        message.save(force_insert=True)
        file_key = envelope.generate_file_key()
        seal_file_keys_for_webhooks(message, file_key, "bob@example.com")
        sealed = SealedFileKey.objects.get(message=message, webhook=webhook)
        assert sealed.webhook_key_id == webhook.encryption_key.key_id
        recovered = envelope.unseal_file_key(
            envelope.decode_key(sealed.sealed_key), private_key
        )
        assert recovered == file_key

    def test_seal_file_keys_for_webhooks__skips_webhooks_without_encryption_key(
        self, org
    ):
        webhook = make_plain_webhook(org, pattern="*@example.com")
        message = make_unsaved_incoming(org)
        message.rcpt_to = "bob@example.com"
        message.save(force_insert=True)
        file_key = envelope.generate_file_key()
        seal_file_keys_for_webhooks(message, file_key, "bob@example.com")
        assert not SealedFileKey.objects.filter(
            message=message, webhook=webhook
        ).exists()

    def test_seal_file_keys_for_webhooks__only_seals_matching_webhooks(self, org):
        webhook, _ = make_encrypted_webhook(org, pattern="*@other.com")
        message = make_unsaved_incoming(org)
        message.rcpt_to = "bob@example.com"
        message.save(force_insert=True)
        file_key = envelope.generate_file_key()
        seal_file_keys_for_webhooks(message, file_key, "bob@example.com")
        assert not SealedFileKey.objects.filter(
            message=message, webhook=webhook
        ).exists()
