import pytest
from dnslib import DNSLabel
from dnslib.dns import QTYPE

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
    def test_root_for__managed_domain(self):
        Organization.objects.create(slug="acme")
        domain = Domain.objects.root_for("acme.open.localhost", include_managed=True)
        assert domain is not None
        assert domain.name == "acme.open.localhost"

    def test_root_for__managed_subdomain(self):
        Organization.objects.create(slug="acme")
        domain = Domain.objects.root_for(
            "mail.acme.open.localhost", include_managed=True
        )
        assert domain is not None
        assert domain.name == "acme.open.localhost"

    def test_root_for__user_domain(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        domain = Domain.objects.root_for("mail.relay.example.com")
        assert domain is not None
        assert domain.name == "example.com"

    def test_root_for__unknown_raises_does_not_exist(self):
        with pytest.raises(Domain.DoesNotExist):
            Domain.objects.root_for("nonexistent.com")


@pytest.mark.django_db
class TestResolve:
    def test_resolve__a_records(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve(DNSLabel("acme.open.localhost"), QTYPE.A)
        assert len(records) >= 1

    def test_resolve__mx_records(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve(DNSLabel("acme.open.localhost"), QTYPE.MX)
        assert len(records) == 1

    def test_resolve__ns_records(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve(DNSLabel("mail.acme.open.localhost"), QTYPE.NS)
        assert len(records) == 2

    def test_resolve__spf_txt(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("mail.relay.example.com"), QTYPE.TXT)
        assert len(records) == 1
        txt_data = b"".join(records[0].rdata.data)
        assert b"v=spf1" in txt_data

    def test_resolve__dmarc_txt_managed_domain(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve(
            DNSLabel("_dmarc.acme.open.localhost"), QTYPE.TXT
        )
        assert len(records) == 1
        txt_data = b"".join(records[0].rdata.data)
        assert b"rua=mailto:" in txt_data
        assert b"@mail.relay.acme.open.localhost" in txt_data

    def test_resolve__cname_return_path(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(
            DNSLabel("rp.mail.relay.example.com"), QTYPE.CNAME
        )
        assert len(records) == 1

    def test_resolve__unknown_domain_returns_empty(self):
        assert DNSResolver().resolve(DNSLabel("unknown.com"), QTYPE.A) == []


@pytest.mark.django_db
class TestResolvePtr:
    def test_resolve_ptr__known_ip(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("1.0.0.127.in-addr.arpa"), QTYPE.PTR)
        assert len(records) == 1

    def test_resolve_ptr__unknown_ip(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(DNSLabel("1.1.1.255.in-addr.arpa"), QTYPE.PTR)
        assert records == []


@pytest.mark.django_db
class TestResolveMtaStsCname:
    def test_resolve__mta_sts_cname(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(
            DNSLabel("mta-sts.mail.relay.example.com"), QTYPE.CNAME
        )
        assert len(records) == 1
        assert "mta-sts." in str(records[0].rdata)

    def test_resolve__mta_sts_cname_managed_domain(self):
        Organization.objects.create(slug="acme")
        records = DNSResolver().resolve(
            DNSLabel("mta-sts.mail.relay.acme.open.localhost"), QTYPE.CNAME
        )
        assert len(records) == 1
        assert "mta-sts." in str(records[0].rdata)

    def test_resolve__mta_sts_no_cname_for_other_subdomains(self):
        org = Organization.objects.create(slug="o")
        Domain.objects.create(name="example.com", org=org)
        records = DNSResolver().resolve(
            DNSLabel("mta-sts.other.example.com"), QTYPE.CNAME
        )
        assert records == []
