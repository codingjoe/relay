import pytest
from django.conf import settings
from dnslib import DNSLabel
from dnslib.dns import QTYPE

from accounts.models import Organization
from domains.models import Domain
from domains.resolver import DNSResolver, txt
from kms import keys as kms_keys


class TestTxt:
    def test_txt__short_value(self):
        assert txt("hello") is not None

    def test_txt__long_value_splits(self):
        assert txt("a" * 300) is not None


class TestDomainQuerySetSignature:
    def test_root_for__requires_keyword_only_managed_scope(self):
        with pytest.raises(TypeError):
            Domain.objects.root_for("example.com")
        with pytest.raises(TypeError):
            Domain.objects.root_for("example.com", True)


class TestDomainQuerySet:
    @pytest.mark.django_db
    def test_root_for__managed_domain(self):
        Organization.objects.create(slug="acme")
        domain = Domain.objects.root_for("acme.open.localhost", include_managed=True)
        assert domain is not None
        assert domain.name == "acme.open.localhost"

    @pytest.mark.django_db
    def test_root_for__managed_subdomain(self):
        Organization.objects.create(slug="acme")
        domain = Domain.objects.root_for(
            "mail.acme.open.localhost", include_managed=True
        )
        assert domain is not None
        assert domain.name == "acme.open.localhost"

    @pytest.mark.django_db
    def test_root_for__can_exclude_managed_domain(self):
        Organization.objects.create(slug="acme")

        with pytest.raises(Domain.DoesNotExist):
            Domain.objects.root_for(
                "mail.acme.open.localhost",
                include_managed=False,
            )

    @pytest.mark.django_db
    def test_root_for__user_domain(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        domain = Domain.objects.root_for(
            "mail.relay.example.com",
            include_managed=False,
        )
        assert domain is not None
        assert domain.name == "example.com"

    @pytest.mark.django_db
    def test_root_for__selects_nested_domain_for_same_org(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        child = Domain.objects.create(name="app.example.com", org=org)

        assert (
            Domain.objects.root_for(
                "mail.app.example.com",
                include_managed=False,
            )
            == child
        )

    @pytest.mark.django_db
    def test_root_for__fails_closed_for_mixed_owners(self):
        parent_org = Organization.objects.create(slug="parent")
        child_org = Organization.objects.create(slug="child")
        Domain.objects.bulk_create(
            [
                Domain(name="example.com", org=parent_org),
                Domain(name="app.example.com", org=child_org),
            ]
        )

        with pytest.raises(Domain.DoesNotExist):
            Domain.objects.root_for(
                "mail.app.example.com",
                include_managed=False,
            )

    @pytest.mark.django_db
    def test_root_for__unknown_raises_does_not_exist(self):
        with pytest.raises(Domain.DoesNotExist):
            Domain.objects.root_for(
                "nonexistent.com",
                include_managed=False,
            )

    def test_root_for__invalid_idna_raises_does_not_exist(self):
        with pytest.raises(Domain.DoesNotExist):
            Domain.objects.root_for(
                "\udcff",
                include_managed=False,
            )

    def test_root_for__empty_name_raises_does_not_exist(self):
        with pytest.raises(Domain.DoesNotExist):
            Domain.objects.root_for(
                "",
                include_managed=False,
            )

    def test_resolve_records__public_smtp_hostname_a_records_without_domain(self):
        records = DNSResolver().resolve_records(
            DNSLabel(settings.RELAY_SMTP_PUBLIC_HOSTNAME),
            QTYPE.A,
        )

        assert {str(record.rdata) for record in records} == set(
            settings.RELAY_DNS_SMTP_IPS
        )


@pytest.mark.django_db
class TestResolve:
    def test_resolve_records__a_records(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve_records(
            DNSLabel("mail.relay.acme.open.localhost"), QTYPE.A
        )
        assert {str(record.rdata) for record in records} == set(
            settings.RELAY_DNS_SMTP_IPS
        )

    def test_resolve_records__does_not_publish_a_for_domain_apex(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        assert DNSResolver().resolve_records(DNSLabel(domain.name), QTYPE.A) == []

    def test_resolve_records__does_not_publish_a_for_other_subdomain(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)

        assert (
            DNSResolver().resolve_records(DNSLabel("other.example.com"), QTYPE.A) == []
        )

    def test_resolve_records__does_not_use_cross_org_nested_domain(self):
        parent_org = Organization.objects.create(slug="parent")
        child_org = Organization.objects.create(slug="child")
        Domain.objects.bulk_create(
            [
                Domain(name="example.com", org=parent_org),
                Domain(name="app.example.com", org=child_org),
            ]
        )

        records = DNSResolver().resolve_records(
            DNSLabel("mail.app.example.com"),
            QTYPE.MX,
        )

        assert records == []

    def test_resolve_records__mx_records(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve_records(
            DNSLabel("acme.open.localhost"), QTYPE.MX
        )
        assert len(records) == 1
        assert str(records[0].rdata.label) == "mail.relay.acme.open.localhost."

    def test_resolve_records__ns_records(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve_records(
            DNSLabel("mail.acme.open.localhost"), QTYPE.NS
        )
        assert {str(record.rdata.label).rstrip(".") for record in records} == set(
            settings.RELAY_DNS_NS_NAMESERVERS
        )

    def test_resolve_records__spf_txt(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve_records(
            DNSLabel("mail.relay.example.com"), QTYPE.TXT
        )
        assert len(records) == 1
        txt_data = b"".join(records[0].rdata.data)
        assert b"v=spf1" in txt_data

    def test_resolve_records__dmarc_txt_managed_domain(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve_records(
            DNSLabel("_dmarc.acme.open.localhost"), QTYPE.TXT
        )
        assert len(records) == 1
        txt_data = b"".join(records[0].rdata.data)
        assert b"rua=mailto:" in txt_data
        assert b"@mail.relay.acme.open.localhost" in txt_data

    def test_resolve_records__publishes_domain_txt_records(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        expected_records = [
            (domain.name, domain.root_spf_record),
            (domain.dmarc_record_name, domain.dmarc_record),
            (f"_dmarc.{domain.sender_domain}", domain.sender_dmarc_record),
            (f"_mta-sts.{domain.name}", domain.mta_sts_record),
            (f"_smtp._tls.{domain.name}", domain.tls_rpt_record),
            (f"_smtp._tls.{domain.sender_domain}", domain.tls_rpt_record),
        ]

        for query_name, expected_value in expected_records:
            records = DNSResolver().resolve_records(DNSLabel(query_name), QTYPE.TXT)
            values = [b"".join(record.rdata.data).decode() for record in records]
            assert expected_value in values, query_name

    def test_resolve_records__publishes_dkim_at_root_and_sender_domain(self):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        selector, _ = domain.dkim_ciphers[0]

        for base in (domain.name, domain.sender_domain):
            records = DNSResolver().resolve_records(
                DNSLabel(f"{selector}._domainkey.{base}"),
                QTYPE.TXT,
            )
            assert len(records) == 1, base
            assert b"v=DKIM1" in b"".join(records[0].rdata.data)

    def test_resolve_records__no_platform_dkim_txt_without_key(self, settings):
        settings.RELAY_DNS_DKIM_IDENTIFIER = "relay"
        selector = f"{settings.RELAY_DNS_DKIM_IDENTIFIER}-platform-rsa1024"

        records = DNSResolver().resolve_records(
            DNSLabel(f"{selector}._domainkey.{settings.RELAY_PLATFORM_DOMAIN}"),
            QTYPE.TXT,
        )

        assert records == []

    def test_resolve_records__unknown_domain_returns_empty(self):
        assert DNSResolver().resolve_records(DNSLabel("unknown.com"), QTYPE.A) == []

    def test_resolve_records__mta_sts_cname(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve_records(
            DNSLabel("mta-sts.mail.relay.example.com"), QTYPE.CNAME
        )
        assert len(records) == 1
        assert str(records[0].rdata) == f"mta-sts.{settings.RELAY_PLATFORM_DOMAIN}."

    def test_resolve_records__mta_sts_cname_takes_priority_for_other_query_types(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)

        records = DNSResolver().resolve_records(
            DNSLabel("mta-sts.example.com"), QTYPE.A
        )

        assert len(records) == 1
        assert records[0].rtype == QTYPE.CNAME
        assert str(records[0].rdata) == "mta-sts.mail.relay.example.com."

    def test_resolve_records__mta_sts_cname_managed_domain(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve_records(
            DNSLabel("mta-sts.mail.relay.acme.open.localhost"), QTYPE.CNAME
        )
        assert len(records) == 1
        assert str(records[0].rdata) == f"mta-sts.{settings.RELAY_PLATFORM_DOMAIN}."

    def test_resolve_records__mta_sts_no_cname_for_other_subdomains(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve_records(
            DNSLabel("mta-sts.other.example.com"), QTYPE.CNAME
        )
        assert records == []


class TestPlatformRecords:
    def test_resolve_records__publishes_platform_dkim_txt(self, settings):
        settings.RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY = (
            kms_keys.generate_rsa_private_key(1024)
        )
        selector = f"{settings.RELAY_DNS_DKIM_IDENTIFIER}-platform-rsa1024"

        records = DNSResolver().resolve_records(
            DNSLabel(f"{selector}._domainkey.{settings.RELAY_PLATFORM_DOMAIN}"),
            QTYPE.TXT,
        )

        assert len(records) == 1
        assert b"v=DKIM1" in b"".join(records[0].rdata.data)
