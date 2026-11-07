import dns.resolver
import pytest
from django.conf import settings
from django.utils import timezone

from accounts.models import Organization
from domains import services
from domains.models import Domain
from domains.services import (
    check_dkim_cname,
    check_dmarc,
    check_mta_sts,
    check_spf,
    check_tls_rpt,
    matches_mta_sts_mx_pattern,
    parse_mta_sts_txt_record,
    verify_domain_dns,
    verify_nameserver_delegation,
)


@pytest.mark.django_db
class TestVerifyNameserverDelegation:
    def test_verify_nameserver_delegation__ok(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        assert verify_nameserver_delegation(domain) is True

    def test_verify_nameserver_delegation__mismatch(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns9.other.com.")
        assert verify_nameserver_delegation(domain) is False

    def test_verify_nameserver_delegation__nxdomain(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert verify_nameserver_delegation(domain) is False

    def test_verify_nameserver_delegation__chased_cname(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "CNAME", "relays.to.")
        dns_resolver.add("relays.to", "NS", "ns1.localhost.", "ns2.localhost.")
        assert verify_nameserver_delegation(domain) is False

    def test_verify_nameserver_delegation__cname_loop(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "CNAME", "relays.to.")
        dns_resolver.add("relays.to.", "CNAME", f"{domain.sender_domain}.")
        assert verify_nameserver_delegation(domain) is False


@pytest.mark.django_db
class TestCheckDmarc:
    def test_check_dmarc__present(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{domain.dmarc_record}"')
        assert check_dmarc(domain) is True

    def test_check_dmarc__requires_reporting_addresses(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.dmarc_record_name, "TXT", '"v=DMARC1; p=none"')
        assert check_dmarc(domain) is False

    def test_check_dmarc__rejects_wrong_rua(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        record = domain.dmarc_record.replace(
            domain.dmarc_reporting_address, "other@example.com"
        )
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{record}"')
        assert check_dmarc(domain) is False

    def test_check_dmarc__rejects_wrong_ruf(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        record = domain.dmarc_record.replace(
            domain.dmarc_ruf_reporting_address, "other@example.com"
        )
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{record}"')
        assert check_dmarc(domain) is False

    def test_check_dmarc__accepts_extra_reporting_addresses(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        record = domain.dmarc_record.replace(
            f"rua=mailto:{domain.dmarc_reporting_address}",
            f"rua=mailto:{domain.dmarc_reporting_address},mailto:other@example.com",
        )
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{record}"')
        assert check_dmarc(domain) is True

    def test_check_dmarc__accepts_size_limit(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        record = domain.dmarc_record.replace(
            f"rua=mailto:{domain.dmarc_reporting_address}",
            f"rua=mailto:{domain.dmarc_reporting_address}!10m",
        )
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{record}"')
        assert check_dmarc(domain) is True

    def test_check_dmarc__joins_split_txt_strings(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            domain.dmarc_record_name,
            "TXT",
            f'"{domain.dmarc_record[:20]}" "{domain.dmarc_record[20:]}"',
        )
        assert check_dmarc(domain) is True

    def test_check_dmarc__rejects_multiple_records(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            domain.dmarc_record_name,
            "TXT",
            f'"{domain.dmarc_record}"',
            f'"{domain.dmarc_record.replace("p=quarantine", "p=none")}"',
        )
        assert check_dmarc(domain) is False

    def test_check_dmarc__absent(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert check_dmarc(domain) is False

    def test_check_dmarc__wrong_prefix(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.name, "TXT", "v=spf1 include:spf.localhost ~all")
        assert check_dmarc(domain) is False


@pytest.mark.django_db
class TestCheckSpf:
    def test_check_spf__present(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        assert check_spf(domain) is True

    def test_check_spf__absent(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.name, "TXT", "v=spf1 include:other.com ~all")
        assert check_spf(domain) is False

    def test_check_spf__nxdomain(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert check_spf(domain) is False


@pytest.mark.django_db
class TestCheckDkimCname:
    def test_check_dkim_cname__present(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        cname_name, _target = domain.dkim_cnames["dkim_rsa2048"]
        dns_resolver.add(
            cname_name,
            # DNS names are case-insensitive.
            "CNAME",
            "RELAY-RSA2048._DOMAINKEY.MAIL.RELAY.EXAMPLE.COM.",
        )
        assert check_dkim_cname(domain, "dkim_rsa2048") is True

    def test_check_dkim_cname__rejects_record_name_as_target(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        cname_name, _target = domain.dkim_cnames["dkim_rsa2048"]
        dns_resolver.add(cname_name, "CNAME", f"{cname_name.upper()}.")
        assert check_dkim_cname(domain, "dkim_rsa2048") is False

    def test_check_dkim_cname__rejects_foreign_target(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        cname_name, _target = domain.dkim_cnames["dkim_rsa2048"]
        dns_resolver.add(
            cname_name,
            "CNAME",
            "relay-rsa2048._domainkey.evil.example.",
        )
        assert check_dkim_cname(domain, "dkim_rsa2048") is False

    def test_check_dkim_cname__independent_per_cipher(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        cname_name, _target = domain.dkim_cnames["dkim_rsa2048"]
        dns_resolver.add(
            cname_name,
            "CNAME",
            "relay-rsa2048._domainkey.mail.relay.example.com.",
        )
        assert check_dkim_cname(domain, "dkim_rsa2048") is True
        assert check_dkim_cname(domain, "dkim_ed25519") is False

    def test_check_dkim_cname__nxdomain(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert check_dkim_cname(domain, "dkim_rsa2048") is False


def test_parse_mta_sts_txt_record__rejects_control_whitespace():
    assert parse_mta_sts_txt_record("v=STSv1;\rid=test") is None


class TestMatchesMtaStsMxPattern:
    @pytest.mark.parametrize(
        ("hostname", "pattern"),
        [
            ("mx1.example.com", "mx1.example.com"),
            ("MX1.Example.com", "mx1.example.com."),
            ("mail.example.com", "*.example.com"),
        ],
    )
    def test_matches_mta_sts_mx_pattern__ok(self, hostname, pattern):
        assert matches_mta_sts_mx_pattern(hostname, pattern) is True

    @pytest.mark.parametrize(
        ("hostname", "pattern"),
        [
            ("mx1.example.com", "mx2.example.com"),
            ("example.com", "*.example.com"),
            ("foo.bar.example.com", "*.example.com"),
            ("mail.example.com", "*.other.com"),
        ],
    )
    def test_matches_mta_sts_mx_pattern__mismatch(self, hostname, pattern):
        assert matches_mta_sts_mx_pattern(hostname, pattern) is False


@pytest.mark.django_db
class TestCheckMtaSts:
    @pytest.fixture
    def domain(self, org, dns_resolver):
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            domain.name,
            "MX",
            *(f"10 {hostname}." for hostname in settings.DNS_MX_HOSTNAMES),
        )
        return domain

    def test_check_mta_sts__requires_txt_and_expected_cname(self, domain, dns_resolver):
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__follows_delegated_txt_cname(self, domain, dns_resolver):
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "CNAME",
            f"{domain.mta_sts_record_cname_target}.",
        )
        dns_resolver.add(
            domain.mta_sts_record_cname_target,
            "TXT",
            f'"{domain.mta_sts_record}"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__rejects_stale_policy_id(self, domain, dns_resolver):
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            '"v=STSv1; id=stale"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__rejects_missing_mx(self, domain, dns_resolver):
        dns_resolver.fail(domain.name, "MX", dns.resolver.NXDOMAIN())
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__rejects_unlisted_mx(self, domain, dns_resolver):
        dns_resolver.add(domain.name, "MX", "10 mx.other.com.")
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__accepts_explicit_mx_hosts(self, domain, dns_resolver):
        domain.mta_sts_mx_hostnames = ["mx1.other.com", "*.mx2.other.com"]
        dns_resolver.add(
            domain.name,
            "MX",
            "10 mx1.other.com.",
            "20 mail.mx2.other.com.",
        )
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__rejects_multi_label_wildcard_match(
        self, domain, dns_resolver
    ):
        domain.mta_sts_mx_hostnames = ["*.other.com"]
        dns_resolver.add(domain.name, "MX", "10 foo.bar.other.com.")
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__joins_split_txt_strings(self, domain, dns_resolver):
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            f'"v=STSv1; " "id={domain.mta_sts_policy_id}"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__rejects_other_cname(self, domain, dns_resolver):
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            "mta-sts.attacker.example.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__rejects_version_prefix(self, domain, dns_resolver):
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv10; id=test"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__requires_non_empty_policy_id(self, domain, dns_resolver):
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv1; id=  "')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    @pytest.mark.parametrize(
        "record",
        [
            "v=stsv1; id=test",
            "v=STSv1; id=invalid-id",
            f"v=STSv1; id={'a' * 33}",
        ],
    )
    def test_check_mta_sts__rejects_invalid_policy_fields(
        self,
        domain,
        dns_resolver,
        record,
    ):
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__accepts_one_candidate_with_unrelated_txt(
        self,
        domain,
        dns_resolver,
    ):
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            '"unrelated=value"',
            f'"v=STSv1; id={domain.mta_sts_policy_id}; extension=value;"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__rejects_multiple_candidate_records(
        self, domain, dns_resolver
    ):
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            '"v=STSv1; id=first"',
            '"v=STSv1; id=second"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    @pytest.mark.parametrize(
        "record",
        [
            "v=STSv1; ID={id}",
            "v=STSv1; id={id}; id=second",
            "v=STSv1; id={id}; malformed",
            "v=STSv1; id={id}; invalid name=value",
            "v=STSv1; id={id}; extension=contains; not-a-field",
        ],
    )
    def test_check_mta_sts__rejects_malformed_tags(
        self,
        domain,
        dns_resolver,
        record,
    ):
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            f'"{record.format(id=domain.mta_sts_policy_id)}"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False


@pytest.mark.django_db
class TestCheckTlsRpt:
    def test_check_tls_rpt__follows_delegated_txt_cname(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "CNAME",
            f"{domain.tls_rpt_record_cname_target}.",
        )
        dns_resolver.add(
            domain.tls_rpt_record_cname_target,
            "TXT",
            f'"v=TLSRPTv1;rua=mailto:{domain.tls_reporting_address}"',
        )

        assert check_tls_rpt(domain) is True

    def test_check_tls_rpt__rejects_multiple_candidate_records(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            '"v=TLSRPTv1;rua=mailto:other@example.com"',
            f'"v=TLSRPTv1;rua=mailto:{domain.tls_reporting_address}"',
        )

        assert check_tls_rpt(domain) is False

    def test_check_tls_rpt__accepts_matching_uri_with_size_limit(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f'"v=TLSRPTv1; rua=mailto:other@example.com,'
            f'mailto:{domain.tls_reporting_address}!10m"',
        )

        assert check_tls_rpt(domain) is True

    def test_check_tls_rpt__joins_split_txt_strings(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f'"v=TLSRPTv1; rua=mail" "to:{domain.tls_reporting_address}"',
        )

        assert check_tls_rpt(domain) is True

    def test_check_tls_rpt__rejects_reporting_uri_prefix(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f"v=TLSRPTv1; rua=mailto:{domain.tls_reporting_address}.attacker",
        )

        assert check_tls_rpt(domain) is False

    def test_check_tls_rpt__requires_exact_version(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f"v=TLSRPTv10; rua=mailto:{domain.tls_reporting_address}",
        )

        assert check_tls_rpt(domain) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    "check_name",
    [
        "verify_nameserver_delegation",
        "check_dmarc",
        "check_spf",
        "check_mta_sts",
        "check_tls_rpt",
    ],
)
def test_dns_record_check__no_nameservers_returns_false(monkeypatch, check_name):
    org = Organization.objects.create(slug="o")
    domain = Domain.objects.create(name="example.com", org=org)

    def raise_no_nameservers(*args, **kwargs):
        raise dns.resolver.NoNameservers

    monkeypatch.setattr(dns.resolver, "resolve", raise_no_nameservers)

    assert getattr(services, check_name)(domain) is False


@pytest.mark.django_db
def test_check_dkim_cname__no_nameservers_returns_false(monkeypatch):
    org = Organization.objects.create(slug="o")
    domain = Domain.objects.create(name="example.com", org=org)

    def raise_no_nameservers(*args, **kwargs):
        raise dns.resolver.NoNameservers

    monkeypatch.setattr(dns.resolver, "resolve", raise_no_nameservers)

    assert check_dkim_cname(domain, "dkim_rsa2048") is False


@pytest.mark.django_db
class TestVerifyDomainDns:
    def test_verify_domain_dns__records_unhandled_dns_error(self, monkeypatch):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        def raise_no_nameservers(domain):
            raise dns.resolver.NoNameservers

        monkeypatch.setattr(services, "check_tls_rpt", raise_no_nameservers)

        services.verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.tls_rpt_status == Domain.Status.ERROR
        assert "nameservers" in domain.tls_rpt_error.lower()

    def test_verify_domain_dns__all_ok_sets_verified(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        for field in ("dkim_rsa2048", "dkim_ed25519"):
            cname_name, target = domain.dkim_cnames[field]
            dns_resolver.add(cname_name, "CNAME", f"{target}.")
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{domain.dmarc_record}"')
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f'"v=TLSRPTv1;rua=mailto:{domain.tls_reporting_address}"',
        )
        dns_resolver.add(domain.name, "MX", f"10 {settings.DNS_MX_HOSTNAMES[0]}.")
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.nameserver_status == Domain.Status.OK
        assert domain.spf_status == Domain.Status.OK
        assert domain.dkim_rsa2048_status == Domain.Status.OK
        assert domain.dkim_ed25519_status == Domain.Status.OK
        assert domain.dmarc_status == Domain.Status.OK
        assert domain.mx_status == Domain.Status.OK
        assert domain.mta_sts_status == Domain.Status.OK
        assert domain.tls_rpt_status == Domain.Status.OK
        assert domain.verified_at is not None

    def test_verify_domain_dns__bumps_modified_at(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        modified_at = domain.modified_at

        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.modified_at > modified_at

    def test_verify_domain_dns__all_fail_sets_errors(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.nameserver_status == Domain.Status.ERROR
        assert domain.spf_status == Domain.Status.ERROR
        assert domain.dkim_rsa2048_status == Domain.Status.ERROR
        assert domain.dkim_ed25519_status == Domain.Status.ERROR
        assert domain.dmarc_status == Domain.Status.ERROR
        assert domain.mx_status == Domain.Status.ERROR
        assert domain.mta_sts_status == Domain.Status.ERROR
        assert domain.tls_rpt_status == Domain.Status.ERROR
        assert domain.verified_at is None
        assert domain.nameserver_error
        assert domain.spf_error
        assert domain.dkim_rsa2048_error
        assert domain.dkim_ed25519_error
        assert domain.dmarc_error
        assert domain.mx_error
        assert domain.mta_sts_error
        assert domain.tls_rpt_error

    def test_verify_domain_dns__error_names_the_record(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)

        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert {
            field: getattr(domain, f"{field}_error")
            for field in (
                *Domain.DELEGATION_CHECK_FIELDS,
                *Domain.SENDING_CHECK_FIELDS,
                *Domain.RECEIVING_CHECK_FIELDS,
                *Domain.REPORTING_CHECK_FIELDS,
            )
        } == {
            "nameserver": "NS record not found or incorrect.",
            "spf": "SPF record not found or incorrect.",
            "dkim_rsa2048": "RSA-2048 DKIM record not found or incorrect.",
            "dkim_ed25519": "Ed25519 DKIM record not found or incorrect.",
            "dmarc": "DMARC record or reporting addresses not found or incorrect.",
            "mx": "MX record not found or incorrect.",
            "mta_sts": "MTA-STS record or MX hosts not found or incorrect.",
            "tls_rpt": "TLS-RPT record not found or incorrect.",
        }

    def test_verify_domain_dns__quick_start_records_verify_the_domain(
        self, dns_resolver
    ):
        """The sending records alone make a domain send, without receiving or hardening."""
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        rsa_cname, _target = domain.dkim_cnames["dkim_rsa2048"]
        dns_resolver.add(
            rsa_cname,
            "CNAME",
            "relay-rsa2048._domainkey.mail.relay.example.com.",
        )
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.is_sending_verified is True
        assert domain.dkim_ed25519_status == Domain.Status.ERROR
        assert domain.mx_status == Domain.Status.ERROR
        assert domain.verified_at is not None

    def test_verify_domain_dns__rejects_foreign_mx(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.name, "MX", "10 mail.other.example.")

        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.mx_status == Domain.Status.ERROR

    def test_verify_domain_dns__partial_pass(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        for field in ("dkim_rsa2048", "dkim_ed25519"):
            cname_name, target = domain.dkim_cnames[field]
            dns_resolver.add(cname_name, "CNAME", f"{target}.")
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.nameserver_status == Domain.Status.OK
        assert domain.spf_status == Domain.Status.ERROR
        assert domain.dkim_rsa2048_status == Domain.Status.OK
        assert domain.dkim_ed25519_status == Domain.Status.OK
        assert domain.dmarc_status == Domain.Status.ERROR
        assert domain.mx_status == Domain.Status.ERROR
        assert domain.mta_sts_status == Domain.Status.ERROR
        assert domain.tls_rpt_status == Domain.Status.ERROR
        assert domain.verified_at is None

    def test_verify_domain_dns__does_not_re_verify(self, dns_resolver):
        org = Organization.objects.create(slug="o")
        old_verified = timezone.now()
        domain = Domain.objects.create(
            name="example.com", org=org, verified_at=old_verified
        )
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        for field in ("dkim_rsa2048", "dkim_ed25519"):
            cname_name, target = domain.dkim_cnames[field]
            dns_resolver.add(cname_name, "CNAME", f"{target}.")
        dns_resolver.add(domain.dmarc_record_name, "TXT", f'"{domain.dmarc_record}"')
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{domain.mta_sts_record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f'"v=TLSRPTv1;rua=mailto:{domain.tls_reporting_address}"',
        )
        dns_resolver.add(domain.name, "MX", f"10 {settings.DNS_MX_HOSTNAMES[0]}.")
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.verified_at == old_verified
