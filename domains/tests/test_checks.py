import dns.resolver
from django.test import override_settings

from domains.checks import check_managed_domain_dns


@override_settings(RELAY_MANAGED_SENDER_DOMAIN="")
def test_check_managed_domain_dns__requires_managed_zone():
    errors = check_managed_domain_dns(None)

    assert [error.id for error in errors] == ["domains.E001"]


@override_settings(
    RELAY_MANAGED_SENDER_DOMAIN="open.example.com",
    RELAY_DNS_NS_NAMESERVERS=["ns1.example.com", "ns2.example.com"],
)
def test_check_managed_domain_dns__accepts_expected_nameservers(dns_resolver):
    dns_resolver.add(
        "open.example.com",
        "NS",
        "NS1.EXAMPLE.COM.",
        "ns2.example.com.",
    )

    assert check_managed_domain_dns(None) == []


@override_settings(
    RELAY_MANAGED_SENDER_DOMAIN="open.example.com",
    RELAY_DNS_NS_NAMESERVERS=["ns1.example.com", "ns2.example.com"],
)
def test_check_managed_domain_dns__reports_nameserver_mismatch(dns_resolver):
    dns_resolver.add("open.example.com", "NS", "ns.other.com.")

    errors = check_managed_domain_dns(None)

    assert [error.id for error in errors] == ["domains.E003"]


def test_check_managed_domain_dns__returns_error_for_unavailable_nameservers(
    monkeypatch,
):
    def raise_no_nameservers(*args, **kwargs):
        raise dns.resolver.NoNameservers

    monkeypatch.setattr(dns.resolver, "resolve", raise_no_nameservers)

    errors = check_managed_domain_dns(None)

    assert [error.id for error in errors] == ["domains.E002"]
