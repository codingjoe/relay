import pytest

from domains.models import Domain
from kms.models import SigningKey
from services.email.mx.models import Webhook


@pytest.mark.django_db
def test_domain_rename__synchronizes_webhook_address_pattern(org):
    domain = Domain.objects.create(name="example.com", org=org)
    webhooks = [
        Webhook.objects.create(
            org=org,
            url=f"https://example.com/{prefix}",
            address_pattern=f"{prefix}@example.com",
            domain=domain,
            signing_key=SigningKey.generate("ed25519"),
        )
        for prefix in ("support", "alerts")
    ]

    domain.name = "renamed.example.com"
    domain.save(update_fields=["name"])

    for webhook, prefix in zip(webhooks, ("support", "alerts"), strict=True):
        webhook.refresh_from_db()
        assert webhook.address_pattern == f"{prefix}@renamed.example.com"


@pytest.mark.django_db
def test_other_domain_update__keeps_webhook_address_pattern(org):
    domain = Domain.objects.create(name="example.com", org=org)
    webhook = Webhook.objects.create(
        org=org,
        url="https://example.com/hook",
        address_pattern="support@example.com",
        domain=domain,
        signing_key=SigningKey.generate("ed25519"),
    )

    domain.verified_at = None
    domain.save(update_fields=["verified_at"])

    webhook.refresh_from_db()
    assert webhook.address_pattern == "support@example.com"
