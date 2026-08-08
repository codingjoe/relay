import dns.resolver
import pytest
from django.utils import timezone

from accounts.models import Organization
from domains.models import Domain


@pytest.mark.django_db
class TestVerifyNameserverDelegation:
    def test_verify_nameserver_delegation__ok(self, dns_resolver):
        from domains.services import verify_nameserver_delegation

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        assert verify_nameserver_delegation(domain) is True

    def test_verify_nameserver_delegation__mismatch(self, dns_resolver):
        from domains.services import verify_nameserver_delegation

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns9.other.com.")
        assert verify_nameserver_delegation(domain) is False

    def test_verify_nameserver_delegation__nxdomain(self, dns_resolver):
        from domains.services import verify_nameserver_delegation

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert verify_nameserver_delegation(domain) is False


@pytest.mark.django_db
class TestCheckDmarc:
    def test_check_dmarc__present(self, dns_resolver):
        from domains.services import check_dmarc

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.dmarc_record_name, "TXT", "v=DMARC1; p=none")
        assert check_dmarc(domain) is True

    def test_check_dmarc__absent(self, dns_resolver):
        from domains.services import check_dmarc

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert check_dmarc(domain) is False

    def test_check_dmarc__wrong_prefix(self, dns_resolver):
        from domains.services import check_dmarc

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.name, "TXT", "v=spf1 include:spf.localhost ~all")
        assert check_dmarc(domain) is False


@pytest.mark.django_db
class TestCheckSpf:
    def test_check_spf__present(self, dns_resolver):
        from domains.services import check_spf

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        assert check_spf(domain) is True

    def test_check_spf__absent(self, dns_resolver):
        from domains.services import check_spf

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.name, "TXT", "v=spf1 include:other.com ~all")
        assert check_spf(domain) is False

    def test_check_spf__nxdomain(self, dns_resolver):
        from domains.services import check_spf

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert check_spf(domain) is False


@pytest.mark.django_db
class TestCheckDkimCname:
    def test_check_dkim_cname__present(self, dns_resolver):
        from domains.services import check_dkim_cname

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        for cname_name, _ in domain.dkim_cnames:
            dns_resolver.add(
                cname_name,
                "CNAME",
                "relay-abc._domainkey.mail.relay.example.com.",
            )
        assert check_dkim_cname(domain) is True

    def test_check_dkim_cname__fails_if_any_cname_missing(self, dns_resolver):
        from domains.services import check_dkim_cname

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        # Add only the first CNAME, leave the other two unresolved
        first_name, _ = domain.dkim_cnames[0]
        dns_resolver.add(
            first_name,
            "CNAME",
            "relay-abc._domainkey.mail.relay.example.com.",
        )
        assert check_dkim_cname(domain) is False

    def test_check_dkim_cname__nxdomain(self, dns_resolver):
        from domains.services import check_dkim_cname

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        assert check_dkim_cname(domain) is False


def test_parse_mta_sts_txt_record__rejects_control_whitespace():
    from domains.services import parse_mta_sts_txt_record

    assert parse_mta_sts_txt_record("v=STSv1;\rid=test") is None


@pytest.mark.django_db
class TestCheckMtaSts:
    def test_check_mta_sts__requires_txt_and_expected_cname(self, dns_resolver):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv1; id=test"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__joins_split_txt_strings(self, dns_resolver):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            '"v=STSv1; " "id=test"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__rejects_other_cname(self, dns_resolver):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv1; id=test"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            "mta-sts.attacker.example.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__rejects_version_prefix(self, dns_resolver):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv10; id=test"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__requires_non_empty_policy_id(self, dns_resolver):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
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
        dns_resolver,
        record,
    ):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{record}"')
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is False

    def test_check_mta_sts__accepts_one_candidate_with_unrelated_txt(
        self,
        dns_resolver,
    ):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            '"unrelated=value"',
            '"v=STSv1; id=test; extension=value;"',
        )
        dns_resolver.add(
            f"mta-sts.{domain.name}",
            "CNAME",
            f"mta-sts.{domain.sender_domain}.",
        )

        assert check_mta_sts(domain) is True

    def test_check_mta_sts__rejects_multiple_candidate_records(self, dns_resolver):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_mta-sts.{domain.name}",
            "TXT",
            '"v=STSv1; id=first"',
            '"v=STSv1; id=second"',
        )

        assert check_mta_sts(domain) is False

    @pytest.mark.parametrize(
        "record",
        [
            "v=STSv1; ID=test",
            "v=STSv1; id=first; id=second",
            "v=STSv1; id=test; malformed",
            "v=STSv1; id=test; invalid name=value",
            "v=STSv1; id=test; extension=contains:semicolon",
        ],
    )
    def test_check_mta_sts__rejects_malformed_tags(
        self,
        dns_resolver,
        record,
    ):
        from domains.services import check_mta_sts

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", f'"{record}"')

        assert check_mta_sts(domain) is False


@pytest.mark.django_db
class TestCheckTlsRpt:
    def test_check_tls_rpt__accepts_matching_uri_with_size_limit(self, dns_resolver):
        from domains.services import check_tls_rpt

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
        from domains.services import check_tls_rpt

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f'"v=TLSRPTv1; rua=mail" "to:{domain.tls_reporting_address}"',
        )

        assert check_tls_rpt(domain) is True

    def test_check_tls_rpt__rejects_reporting_uri_prefix(self, dns_resolver):
        from domains.services import check_tls_rpt

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(
            f"_smtp._tls.{domain.name}",
            "TXT",
            f"v=TLSRPTv1; rua=mailto:{domain.tls_reporting_address}.attacker",
        )

        assert check_tls_rpt(domain) is False

    def test_check_tls_rpt__requires_exact_version(self, dns_resolver):
        from domains.services import check_tls_rpt

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
        "check_dkim_cname",
        "check_mta_sts",
        "check_tls_rpt",
    ],
)
def test_dns_record_check__no_nameservers_returns_false(monkeypatch, check_name):
    from domains import services

    org = Organization.objects.create(slug="o")
    domain = Domain.objects.create(name="example.com", org=org)

    def raise_no_nameservers(*args, **kwargs):
        raise dns.resolver.NoNameservers

    monkeypatch.setattr(dns.resolver, "resolve", raise_no_nameservers)

    assert getattr(services, check_name)(domain) is False


@pytest.mark.django_db
class TestVerifyDomainDns:
    def test_verify_domain_dns__records_unhandled_dns_error(self, monkeypatch):
        from domains import services

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
        from domains.services import verify_domain_dns

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        for cname_name, _ in domain.dkim_cnames:
            dns_resolver.add(
                cname_name,
                "CNAME",
                "relay-abc._domainkey.mail.relay.example.com.",
            )
        dns_resolver.add(domain.dmarc_record_name, "TXT", "v=DMARC1; p=none")
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv1; id=test"')
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
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.nameserver_status == Domain.Status.OK
        assert domain.spf_status == Domain.Status.OK
        assert domain.dkim_status == Domain.Status.OK
        assert domain.dmarc_status == Domain.Status.OK
        assert domain.mta_sts_status == Domain.Status.OK
        assert domain.tls_rpt_status == Domain.Status.OK
        assert domain.verified_at is not None

    def test_verify_domain_dns__all_fail_sets_errors(self, dns_resolver):
        from domains.services import verify_domain_dns

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.nameserver_status == Domain.Status.ERROR
        assert domain.spf_status == Domain.Status.ERROR
        assert domain.dkim_status == Domain.Status.ERROR
        assert domain.dmarc_status == Domain.Status.ERROR
        assert domain.mta_sts_status == Domain.Status.ERROR
        assert domain.tls_rpt_status == Domain.Status.ERROR
        assert domain.verified_at is None
        assert domain.nameserver_error
        assert domain.spf_error
        assert domain.dkim_error
        assert domain.dmarc_error
        assert domain.mta_sts_error
        assert domain.tls_rpt_error

    def test_verify_domain_dns__partial_pass(self, dns_resolver):
        from domains.services import verify_domain_dns

        org = Organization.objects.create(slug="o")
        domain = Domain.objects.create(name="example.com", org=org)
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        for cname_name, _ in domain.dkim_cnames:
            dns_resolver.add(
                cname_name,
                "CNAME",
                "relay-abc._domainkey.mail.relay.example.com.",
            )
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.nameserver_status == Domain.Status.OK
        assert domain.spf_status == Domain.Status.ERROR
        assert domain.dkim_status == Domain.Status.OK
        assert domain.dmarc_status == Domain.Status.ERROR
        assert domain.mta_sts_status == Domain.Status.ERROR
        assert domain.tls_rpt_status == Domain.Status.ERROR
        assert domain.verified_at is None

    def test_verify_domain_dns__does_not_re_verify(self, dns_resolver):
        from domains.services import verify_domain_dns

        org = Organization.objects.create(slug="o")
        old_verified = timezone.now()
        domain = Domain.objects.create(
            name="example.com", org=org, verified_at=old_verified
        )
        dns_resolver.add(domain.sender_domain, "NS", "ns1.localhost.", "ns2.localhost.")
        dns_resolver.add(
            domain.name, "TXT", f"v=spf1 include:{domain.sender_domain} ~all"
        )
        for cname_name, _ in domain.dkim_cnames:
            dns_resolver.add(
                cname_name,
                "CNAME",
                "relay-abc._domainkey.mail.relay.example.com.",
            )
        dns_resolver.add(domain.dmarc_record_name, "TXT", "v=DMARC1; p=none")
        dns_resolver.add(f"_mta-sts.{domain.name}", "TXT", '"v=STSv1; id=test"')
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
        verify_domain_dns(domain)

        domain.refresh_from_db()
        assert domain.verified_at == old_verified
