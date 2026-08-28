import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from domains.models import Domain, validate_domain_name
from kms import keys as kms_keys


class TestValidateDomainName:
    def test_validate_domain_name__accepts_valid_domain(self):
        validate_domain_name("example.com")

    def test_validate_domain_name__accepts_subdomain(self):
        validate_domain_name("sub.example.com")

    def test_validate_domain_name__accepts_managed_domain(self):
        validate_domain_name("open.localhost")

    def test_validate_domain_name__rejects_dot(self):
        with pytest.raises(ValidationError):
            validate_domain_name(".")

    def test_validate_domain_name__rejects_empty(self):
        with pytest.raises(ValidationError):
            validate_domain_name("")

    def test_validate_domain_name__rejects_single_label(self):
        with pytest.raises(ValidationError):
            validate_domain_name("example")

    def test_validate_domain_name__rejects_double_dot(self):
        with pytest.raises(ValidationError):
            validate_domain_name("example..com")

    def test_validate_domain_name__rejects_leading_hyphen(self):
        with pytest.raises(ValidationError):
            validate_domain_name("-example.com")


class TestGenerateRsaPrivateKey:
    def test_generate_rsa_private_key__returns_pem(self):
        pem = kms_keys.generate_rsa_private_key(2048)
        assert pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert isinstance(
            kms_keys.load(kms_keys.keystore.encrypt(pem)),
            rsa.RSAPrivateKey,
        )


class TestDomainPropertiesNoDb:
    def test_sender_domain__appends_prefix(self):
        assert Domain(name="example.com").sender_domain == "mail.relay.example.com"

    def test_dmarc_record_name__prepends_dmarc(self):
        assert Domain(name="example.com").dmarc_record_name == "_dmarc.example.com"

    def test_is_verified__false(self):
        assert Domain(name="example.com").is_verified is False

    def test_is_verified__true(self):
        from django.utils import timezone

        assert (
            Domain(name="example.com", verified_at=timezone.now()).is_verified is True
        )

    def test_sender_domain__appends_prefix_for_managed(self):
        assert (
            Domain(name="acme.open.localhost", is_managed=True).sender_domain
            == "mail.relay.acme.open.localhost"
        )

    def test_fbl_reporting_address__uses_fbl_local_part(self):
        from django.conf import settings

        assert Domain(name="example.com").fbl_reporting_address == (
            f"{settings.RELAY_FBL_LOCAL_PART}@mail.relay.example.com"
        )

    def test_spf_record__includes_spf_include(self):
        record = Domain(name="example.com").root_spf_record
        assert "v=spf1" in record
        assert "include:mail.relay.example.com" in record

    def test_str__labels_managed_domain(self):
        assert str(Domain(name="open.example.com", is_managed=True)) == (
            "open.example.com (managed)"
        )


class TestDomainClean:
    @pytest.mark.parametrize(
        "name",
        ["app.open.relay.example.com", "open.relay.example.com"],
    )
    def test_clean__rejects_relay_managed_names(self, name, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relay.example.com"
        settings.RELAY_MANAGED_SENDER_DOMAIN = "open.relay.example.com"

        with pytest.raises(ValidationError):
            Domain(name=name).clean()

    def test_clean__allows_managed_domain(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relay.example.com"
        settings.RELAY_MANAGED_SENDER_DOMAIN = "open.relay.example.com"

        Domain(name="acme.open.relay.example.com", is_managed=True).clean()

    def test_clean__rejects_unicode_dot_beneath_managed_zone(self, settings):
        settings.RELAY_PLATFORM_DOMAIN = "relay.example.com"
        settings.RELAY_MANAGED_SENDER_DOMAIN = "open.relay.example.com"

        with pytest.raises(ValidationError):
            Domain(name="app。open.relay.example.com").clean()

    @pytest.mark.django_db
    def test_save__rejects_cross_org_child_domain(self):
        from accounts.models import Organization

        parent_org = Organization.objects.create(slug="parent")
        child_org = Organization.objects.create(slug="child")
        Domain.objects.create(name="example.com", org=parent_org)

        with pytest.raises(ValidationError):
            Domain.objects.create(name="app.example.com", org=child_org)

    @pytest.mark.django_db
    def test_save__rejects_cross_org_parent_domain(self):
        from accounts.models import Organization

        child_org = Organization.objects.create(slug="child")
        parent_org = Organization.objects.create(slug="parent")
        Domain.objects.create(name="app.example.com", org=child_org)

        with pytest.raises(ValidationError):
            Domain.objects.create(name="example.com", org=parent_org)

    @pytest.mark.django_db
    def test_save__allows_nested_domains_for_same_org(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)

        domain = Domain.objects.create(name="app.example.com", org=org)

        assert domain.pk is not None

    @pytest.mark.django_db
    def test_save__rejects_unicode_dot_cross_org_child(self):
        from accounts.models import Organization

        parent_org = Organization.objects.create(slug="parent")
        child_org = Organization.objects.create(slug="child")
        Domain.objects.create(name="example.com", org=parent_org)

        with pytest.raises(ValidationError):
            Domain.objects.create(name="app。example.com", org=child_org)


@pytest.mark.django_db
class TestDomainSave:
    def test_save__requires_organization(self):
        with pytest.raises(IntegrityError), transaction.atomic():
            Domain.objects.create(name="example.com")

    def test_save__creates_dkim_keys(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert domain.dkim_key_rsa2048 is not None
        assert domain.dkim_key_rsa1024 is not None
        assert domain.dkim_key_ed25519 is not None

    def test_save__normalizes_name_to_lowercase(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="Example.COM", org=org)

        assert domain.name == "example.com"
        assert Domain.objects.filter(name="example.com").exists()

    def test_save__stores_unicode_name_as_ascii_idna(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="éxample.com", org=org)

        assert domain.name == "xn--xample-9ua.com"

    def test_save__rejects_idna_alias_owned_by_other_org(self):
        from accounts.models import Organization

        unicode_org = Organization.objects.create(slug="unicode")
        ascii_org = Organization.objects.create(slug="ascii")
        Domain.objects.create(name="éxample.com", org=unicode_org)

        with pytest.raises(ValidationError):
            Domain.objects.create(name="xn--xample-9ua.com", org=ascii_org)

    def test_save__does_not_duplicate_dkim_keys(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        first = domain.dkim_key_rsa2048
        domain.save()
        assert domain.dkim_key_rsa2048 == first


@pytest.mark.django_db
class TestDkimCiphers:
    def test_dkim_ciphers__returns_all_three_with_prefix(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        selectors = [selector for selector, _ in domain.dkim_ciphers]
        assert selectors == ["relay-rsa2048", "relay-rsa1024", "relay-ed25519"]

    def test_dkim_ciphers__all_keys_present(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        for _, key in domain.dkim_ciphers:
            assert key is not None


@pytest.mark.django_db
class TestDkimCnames:
    def test_dkim_cnames__one_per_cipher(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        cnames = domain.dkim_cnames
        assert len(cnames) == 3
        for name, target in cnames:
            assert name.startswith("relay-")
            assert name.endswith("._domainkey.example.com")
            assert target.endswith("._domainkey.mail.relay.example.com")

    def test_dkim_cnames__managed_domain_uses_sender_subdomain(self):
        from accounts.models import Organization

        Organization.objects.create(slug="acme")
        domain = Domain.objects.get(name="acme.open.localhost")
        for name, target in domain.dkim_cnames:
            assert name.endswith("._domainkey.acme.open.localhost")
            assert target.endswith("._domainkey.mail.relay.acme.open.localhost")


@pytest.mark.django_db
class TestDomainGetAbsoluteUrl:
    def test_get_absolute_url__returns_detail_url(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="acme")
        domain = Domain.objects.create(name="example.com", org=org)
        url = domain.get_absolute_url()
        assert url is not None
        assert f"/org/{org.slug}/email/domains/{domain.pk}" in url


class TestMtaStsRecord:
    def test_mta_sts_record__includes_sts_version(self):
        assert Domain(name="example.com").mta_sts_record.startswith("v=STSv1;")

    def test_mta_sts_record__includes_policy_id(self):
        record = Domain(name="example.com").mta_sts_record
        assert "id=" in record


class TestDmarcRecord:
    def test_dmarc_record__uses_quarantine_policy(self):
        assert "p=quarantine" in Domain(name="example.com").dmarc_record

    def test_dmarc_record__uses_quarantine_subdomain_policy(self):
        assert "sp=quarantine" in Domain(name="example.com").dmarc_record

    def test_dmarc_record__does_not_use_none_policy(self):
        assert "p=none" not in Domain(name="example.com").dmarc_record


class TestSenderDmarcRecord:
    def test_sender_dmarc_record__uses_quarantine_policy(self):
        assert "p=quarantine" in Domain(name="example.com").sender_dmarc_record

    def test_sender_dmarc_record__does_not_use_none_policy(self):
        assert "p=none" not in Domain(name="example.com").sender_dmarc_record
