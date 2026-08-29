import datetime

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.models import Organization
from services.email.msa.models import SuppressionEntry


class TestHashAddress:
    def test_hash_address__same_email_same_hash(self):
        h1 = SuppressionEntry.hash_address("user@example.com")
        h2 = SuppressionEntry.hash_address("user@example.com")
        assert h1 == h2

    def test_hash_address__case_insensitive(self):
        h1 = SuppressionEntry.hash_address("User@Example.COM")
        h2 = SuppressionEntry.hash_address("user@example.com")
        assert h1 == h2

    def test_hash_address__different_emails_different_hashes(self):
        h1 = SuppressionEntry.hash_address("alice@example.com")
        h2 = SuppressionEntry.hash_address("bob@example.com")
        assert h1 != h2

    def test_hash_address__empty_email_raises(self):
        with pytest.raises(ValidationError):
            SuppressionEntry.hash_address("")

    def test_hash_address__invalid_email_raises(self):
        with pytest.raises(ValidationError):
            SuppressionEntry.hash_address("not-an-email")

    def test_salt__is_class_path(self):
        assert SuppressionEntry.salt() == "services.email.msa.models.SuppressionEntry"


class TestCreateOrUpdate:
    @pytest.mark.django_db
    def test_creates_new_entry(self):
        org = Organization.objects.create(slug="o")
        entry, created = SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        assert created
        assert entry.org == org
        assert entry.reason == SuppressionEntry.Reason.MANUAL
        assert entry.address_hash == SuppressionEntry.hash_address("bob@example.com")

    @pytest.mark.django_db
    def test_updates_existing_entry(self):
        org = Organization.objects.create(slug="o")
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        entry, created = SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.BOUNCE
        )
        assert not created
        assert entry.reason == SuppressionEntry.Reason.BOUNCE

    @pytest.mark.django_db
    def test_separate_orgs_get_separate_entries(self):
        org1 = Organization.objects.create(slug="o1")
        org2 = Organization.objects.create(slug="o2")
        e1, c1 = SuppressionEntry.objects.create_or_update(
            org=org1, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        e2, c2 = SuppressionEntry.objects.create_or_update(
            org=org2, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        assert c1 and c2
        assert e1 != e2


class TestIsSuppressed:
    @pytest.mark.django_db
    def test_manual_entry_suppresses_for_own_org(self):
        org = Organization.objects.create(slug="o")
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        assert SuppressionEntry.objects.is_suppressed(org, "bob@example.com")

    @pytest.mark.django_db
    def test_manual_entry_does_not_suppress_for_other_org(self):
        org1 = Organization.objects.create(slug="o1")
        org2 = Organization.objects.create(slug="o2")
        SuppressionEntry.objects.create_or_update(
            org=org1, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        assert not SuppressionEntry.objects.is_suppressed(org2, "bob@example.com")

    @pytest.mark.django_db
    def test_bounce_entry_suppresses_globally_within_30_days(self):
        org1 = Organization.objects.create(slug="o1")
        org2 = Organization.objects.create(slug="o2")
        SuppressionEntry.objects.create_or_update(
            org=org1, email="bob@example.com", reason=SuppressionEntry.Reason.BOUNCE
        )
        assert SuppressionEntry.objects.is_suppressed(org2, "bob@example.com")

    @pytest.mark.django_db
    def test_bounce_entry_does_not_suppress_after_30_days(self):
        org1 = Organization.objects.create(slug="o1")
        org2 = Organization.objects.create(slug="o2")
        entry, _ = SuppressionEntry.objects.create_or_update(
            org=org1, email="bob@example.com", reason=SuppressionEntry.Reason.BOUNCE
        )
        entry.created_at = timezone.now() - datetime.timedelta(days=31)
        entry.save(update_fields=["created_at"])
        assert not SuppressionEntry.objects.is_suppressed(org2, "bob@example.com")

    @pytest.mark.django_db
    def test_not_suppressed_when_no_entries(self):
        org = Organization.objects.create(slug="o")
        assert not SuppressionEntry.objects.is_suppressed(org, "nobody@example.com")


class TestEmailLookup:
    @pytest.mark.django_db
    def test_filter_by_email_finds_entry(self):
        org = Organization.objects.create(slug="o")
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        found = SuppressionEntry.objects.filter(
            org=org, address_hash__email="bob@example.com"
        )
        assert found.count() == 1

    @pytest.mark.django_db
    def test_filter_by_email_case_insensitive(self):
        org = Organization.objects.create(slug="o")
        SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        found = SuppressionEntry.objects.filter(
            org=org, address_hash__email="BOB@example.com"
        )
        assert found.count() == 1

    @pytest.mark.django_db
    def test_filter_by_email_no_match(self):
        org = Organization.objects.create(slug="o")
        found = SuppressionEntry.objects.filter(
            org=org, address_hash__email="nobody@example.com"
        )
        assert found.count() == 0


class TestSuppressionEntryStr:
    @pytest.mark.django_db
    def test_str__shows_org_and_truncated_hash(self):
        org = Organization.objects.create(slug="acme")
        entry, _ = SuppressionEntry.objects.create_or_update(
            org=org, email="bob@example.com", reason=SuppressionEntry.Reason.MANUAL
        )
        s = str(entry)
        assert "acme" in s
        assert "manual" in s
        assert SuppressionEntry.hash_address("bob@example.com")[:12] in s
