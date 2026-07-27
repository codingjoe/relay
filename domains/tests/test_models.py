import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from domains.models import Domain, generate_verification_token
from kms import keys as kms_keys


class TestGenerateVerificationToken:
    def test_generate_verification_token__length(self):
        assert len(generate_verification_token()) == 16

    def test_generate_verification_token__charset(self):
        assert generate_verification_token().isalnum()


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

    def test_dkim_signing_domain__is_domain_name(self):
        assert Domain(name="example.com").dkim_signing_domain == "example.com"

    def test_dmarc_record_name__prepends_dmarc(self):
        assert Domain(name="example.com").dmarc_record_name == "_dmarc.example.com"

    def test_is_verified__false(self):
        assert Domain(name="example.com").is_verified is False

    def test_is_verified__true(self):
        from django.utils import timezone

        assert (
            Domain(name="example.com", verified_at=timezone.now()).is_verified is True
        )

    def test_is_system__true_for_no_org(self):
        assert Domain(name="open.localhost", org=None).is_system is True

    def test_spf_record__includes_spf_include(self):
        record = Domain(name="example.com").root_spf_record
        assert "v=spf1" in record
        assert "include:mail.relay.example.com" in record

    def test_return_path_domain__uses_prefix(self):
        assert (
            Domain(name="example.com").return_path_domain == "rp.mail.relay.example.com"
        )

    def test_verification_record_name__uses_prefix(self):
        assert (
            Domain(name="example.com").verification_record_name
            == "relay-verification.mail.relay.example.com"
        )

    def test_verification_record__includes_token(self):
        record = Domain(
            name="example.com", verification_token="ABC123"
        ).verification_record
        assert "relay-verification" in record
        assert "ABC123" in record


@pytest.mark.django_db
class TestDomainSave:
    def test_save__creates_dkim_keys(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert domain.dkim_key_rsa2048 is not None
        assert domain.dkim_key_rsa1024 is not None
        assert domain.dkim_key_ed25519 is not None

    def test_save__does_not_duplicate_dkim_keys(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        first = domain.dkim_key_rsa2048
        domain.save()
        assert domain.dkim_key_rsa2048 == first


@pytest.mark.django_db
class TestDkimKeyProperties:
    def test_dkim_ciphers__returns_all_three(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        selectors = [selector for selector, _ in domain.dkim_ciphers]
        assert selectors == ["rsa2048", "rsa1024", "ed25519"]

    def test_dkim_public_key_b64__valid_base64(self):
        import base64 as b64mod

        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        b64mod.b64decode(domain.dkim_public_key_b64, validate=True)

    def test_dkim_record__contains_public_key(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        record = domain.dkim_record
        assert "v=DKIM1" in record
        assert domain.dkim_public_key_b64 in record

    def test_dkim_selector__is_rsa2048(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert domain.dkim_selector == "relay-rsa2048"


@pytest.mark.django_db
class TestDkimRecordNames:
    def test_dkim_record_name__user_domain_uses_sender_subdomain(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert domain.dkim_record_name.startswith("relay-")
        assert domain.dkim_record_name.endswith("._domainkey.mail.relay.example.com")

    def test_dkim_record_name__system_domain_uses_apex(self):
        domain = Domain.objects.create(name="open.localhost", org=None)
        assert domain.dkim_record_name.startswith("relay-")
        assert domain.dkim_record_name.endswith("._domainkey.open.localhost")

    def test_dkim_cname_name__uses_root_domain(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert domain.dkim_cname_name.startswith("relay-")
        assert domain.dkim_cname_name.endswith("._domainkey.example.com")

    def test_dkim_cname_target__equals_record_name(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert domain.dkim_cname_target == domain.dkim_record_name


@pytest.mark.django_db
class TestDomainIsSystem:
    def test_is_system__false_for_org(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="o")
        assert Domain(name="example.com", org=org).is_system is False


@pytest.mark.django_db
class TestDomainGetAbsoluteUrl:
    def test_get_absolute_url__returns_detail_url(self):
        from accounts.models import Organization

        org = Organization.objects.create(slug="acme")
        domain = Domain.objects.create(name="example.com", org=org)
        url = domain.get_absolute_url()
        assert url is not None
        assert f"/org/{org.slug}/email/domains/{domain.pk}" in url

    def test_get_absolute_url__none_for_system_domain(self):
        domain = Domain.objects.create(name="system.com", org=None)
        assert domain.get_absolute_url() is None
