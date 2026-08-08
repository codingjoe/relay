import pytest

from accounts.models import Organization
from domains.models import Domain


@pytest.mark.django_db
class TestSynchronizeManagedDomain:
    def test_create__creates_verified_managed_domain(self, settings):
        org = Organization.objects.create(slug="acme")

        domain = Domain.objects.get(org=org, is_managed=True)
        assert domain.name == f"acme.{settings.RELAY_MANAGED_SENDER_DOMAIN}"
        assert domain.verified_at is not None
        assert domain.dns_checked_at is not None
        assert {
            domain.nameserver_status,
            domain.spf_status,
            domain.dkim_status,
            domain.dmarc_status,
            domain.mta_sts_status,
            domain.tls_rpt_status,
        } == {Domain.Status.OK}

    def test_slug_change__renames_existing_managed_domain(self, settings):
        org = Organization.objects.create(slug="acme")
        domain = Domain.objects.get(org=org, is_managed=True)
        domain_id = domain.pk
        key_ids = (
            domain.dkim_key_rsa2048_id,
            domain.dkim_key_rsa1024_id,
            domain.dkim_key_ed25519_id,
        )

        org.slug = "renamed"
        org.save(update_fields=["slug"])

        domain.refresh_from_db()
        assert domain.pk == domain_id
        assert domain.name == f"renamed.{settings.RELAY_MANAGED_SENDER_DOMAIN}"
        assert (
            domain.dkim_key_rsa2048_id,
            domain.dkim_key_rsa1024_id,
            domain.dkim_key_ed25519_id,
        ) == key_ids
        assert Domain.objects.filter(org=org, is_managed=True).count() == 1
