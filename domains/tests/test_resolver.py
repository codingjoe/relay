import pytest
from dnslib import DNSLabel

from accounts.models import Organization
from domains.models import Domain
from domains.resolver import DNSResolver, txt


class TestTxt:
    def test_txt__short_value(self):
        assert txt("hello") is not None

    def test_txt__long_value_splits(self):
        assert txt("a" * 300) is not None


@pytest.mark.django_db
class TestDomainQuerySet:
    def test_zone_for__system_domain(self):
        Domain.objects.create(name="open.localhost", org=None)
        domain = Domain.objects.zone_for("open.localhost")
        assert domain is not None
        assert domain.name == "open.localhost"

    def test_zone_for__system_subdomain(self):
        Domain.objects.create(name="open.localhost", org=None)
        domain = Domain.objects.zone_for("mail.open.localhost")
        assert domain is not None
        assert domain.name == "open.localhost"

    def test_zone_for__user_domain(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        domain = Domain.objects.zone_for("mail.relay.example.com")
        assert domain is not None
        assert domain.name == "example.com"

    def test_zone_for__unknown_returns_none(self):
        assert Domain.objects.zone_for("nonexistent.com") is None


@pytest.mark.django_db
class TestResolve:
    def test_resolve__a_records(self):
        Domain.objects.create(name="open.localhost", org=None)
        records = DNSResolver().resolve(DNSLabel("open.localhost"), "A")
        assert len(records) >= 1

    def test_resolve__mx_records(self):
        Domain.objects.create(name="open.localhost", org=None)
        records = DNSResolver().resolve(DNSLabel("open.localhost"), "MX")
        assert len(records) == 1

    def test_resolve__ns_records(self):
        Domain.objects.create(name="open.localhost", org=None)
        records = DNSResolver().resolve(DNSLabel("mail.relay.open.localhost"), "NS")
        assert len(records) == 2

    def test_resolve__spf_txt(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("mail.relay.example.com"), "TXT")
        assert len(records) == 1
        txt_data = b"".join(records[0].rdata.data)
        assert b"v=spf1" in txt_data

    def test_resolve__dmarc_txt_system_domain(self):
        Domain.objects.create(name="open.localhost", org=None)
        records = DNSResolver().resolve(DNSLabel("_dmarc.open.localhost"), "TXT")
        assert len(records) == 1

    def test_resolve__cname_return_path(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("rp.mail.relay.example.com"), "CNAME")
        assert len(records) == 1

    def test_resolve__unknown_domain_returns_empty(self):
        assert DNSResolver().resolve(DNSLabel("unknown.com"), "A") == []


@pytest.mark.django_db
class TestResolvePtr:
    def test_resolve_ptr__known_ip(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("1.0.0.127.in-addr.arpa"), "PTR")
        assert len(records) == 1

    def test_resolve_ptr__unknown_ip(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("1.1.1.255.in-addr.arpa"), "PTR")
        assert records == []


@pytest.mark.django_db
class TestResolveMtaStsCname:
    def test_resolve__mta_sts_cname(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(
            DNSLabel("mta-sts.mail.relay.example.com"), "CNAME"
        )
        assert len(records) == 1
        assert "mta-sts." in str(records[0].rdata)

    def test_resolve__mta_sts_cname_system_domain(self):
        Domain.objects.create(name="open.localhost", org=None)
        records = DNSResolver().resolve(DNSLabel("mta-sts.open.localhost"), "CNAME")
        assert len(records) == 1
        assert "mta-sts." in str(records[0].rdata)

    def test_resolve__mta_sts_no_cname_for_other_subdomains(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("mta-sts.other.example.com"), "CNAME")
        assert records == []
