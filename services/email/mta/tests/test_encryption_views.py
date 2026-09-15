import pytest
from django.core.files.base import ContentFile

from domains.models import Domain
from kms import envelope
from kms.models import SigningKey
from services.email.mta.models import (
    IncomingMessage,
    Webhook,
    WebhookEncryptionKey,
)


def make_webhook(org, pattern="*@app.acme.com"):
    signing_key = SigningKey.generate("ed25519")
    domain = Domain.objects.create(name="app.acme.com", org=org)
    return Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        name="My hook",
        address_pattern=pattern,
        domain=domain,
        signing_key=signing_key,
    )


def make_webhook_encryption_key(webhook):
    pair = envelope.generate_x25519_keypair()
    return WebhookEncryptionKey.objects.create(
        webhook=webhook,
        public_key=envelope.encode_key(pair.public_key),
        key_id=envelope.key_fingerprint(pair.public_key),
    )


def webhook_key_payload():
    pair = envelope.generate_x25519_keypair()
    return {
        "public_key": envelope.encode_key(pair.public_key),
        "key_id": envelope.key_fingerprint(pair.public_key),
    }


def make_incoming(org, sealed_file_key="", org_encryption_key_id=""):
    domain = Domain.objects.get(org=org, is_managed=True)
    msg = IncomingMessage(
        org=org,
        domain=domain,
        receiving_domain=domain.name,
        mail_from="alice@example.com",
        rcpt_to="bob@example.com",
        subject="hi",
        message_id="<abc@example.com>",
    )
    msg.raw_body.save(f"{msg.id}.eml", ContentFile(b"raw body"), save=False)
    msg.sealed_file_key = sealed_file_key
    msg.org_encryption_key_id = org_encryption_key_id
    msg.save(force_insert=True)
    return msg


@pytest.mark.django_db
class TestWebhookEncryptionKeyView:
    def test_post__creates_webhook_key(self, client, user, org):
        webhook = make_webhook(org)
        client.force_login(user)
        response = client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/encryption-key/",
            webhook_key_payload(),
            content_type="application/json",
        )
        assert response.status_code == 201
        assert WebhookEncryptionKey.objects.filter(webhook=webhook).exists()

    def test_post__updates_existing_key(self, client, user, org):
        webhook = make_webhook(org)
        existing = make_webhook_encryption_key(webhook)
        client.force_login(user)
        payload = webhook_key_payload()
        response = client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/encryption-key/",
            payload,
            content_type="application/json",
        )
        assert response.status_code == 201
        existing.refresh_from_db()
        assert existing.public_key == payload["public_key"]
        assert existing.key_id == payload["key_id"]

    def test_delete__removes_webhook_key(self, client, user, org):
        webhook = make_webhook(org)
        make_webhook_encryption_key(webhook)
        client.force_login(user)
        response = client.delete(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/encryption-key/"
        )
        assert response.status_code == 204
        assert not WebhookEncryptionKey.objects.filter(webhook=webhook).exists()

    def test_post__non_member_gets_404(self, client, other_user, org):
        webhook = make_webhook(org)
        client.force_login(other_user)
        response = client.post(
            f"/org/{org.slug}/email/webhooks/{webhook.pk}/encryption-key/",
            webhook_key_payload(),
            content_type="application/json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestSealedFileKeyView:
    def test_get__returns_sealed_key(self, client, user, org):
        msg = make_incoming(
            org,
            sealed_file_key="sealed-file-key",
            org_encryption_key_id="key-id-123",
        )
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/email/messages/{msg.id}/sealed-key")
        assert response.status_code == 200
        body = response.json()
        assert body["sealed_file_key"] == "sealed-file-key"
        assert body["org_encryption_key_id"] == "key-id-123"

    def test_get__returns_404_for_unencrypted_message(self, client, user, org):
        msg = make_incoming(org)
        client.force_login(user)
        response = client.get(f"/org/{org.slug}/email/messages/{msg.id}/sealed-key")
        assert response.status_code == 404

    def test_get__non_member_gets_404(self, client, other_user, org):
        msg = make_incoming(org, sealed_file_key="sealed-file-key")
        client.force_login(other_user)
        response = client.get(f"/org/{org.slug}/email/messages/{msg.id}/sealed-key")
        assert response.status_code == 404
