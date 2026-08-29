import dns.resolver
import pytest
from django.db.utils import DatabaseError

from accounts.models import Organization
from domains.checks import check_managed_domain_dns, check_platform_domain
from domains.models import Domain, DomainQuerySet, canonicalize_domain_name


@pytest.mark.django_db
def test_check_platform_domain__warns_without_platform_domain():
    warnings = check_platform_domain(None)

    assert [warning.id for warning in warnings] == ["domains.W001"]


@pytest.mark.django_db
def test_check_platform_domain__warns_when_dkim_keys_missing(settings):
    platform_org = Organization.objects.create(slug="platform-org")
    platform = Domain.objects.create(
        name=canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN),
        org=platform_org,
        is_platform=True,
    )
    Domain.objects.filter(pk=platform.pk).update(dkim_key_rsa1024=None)

    warnings = check_platform_domain(None)

    assert [warning.id for warning in warnings] == ["domains.W002"]
    assert "dkim_key_rsa1024" in warnings[0].msg


@pytest.mark.django_db
def test_check_platform_domain__accepts_provisioned_platform_domain(settings):
    platform_org = Organization.objects.create(slug="platform-org")
    Domain.objects.create(
        name=canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN),
        org=platform_org,
        is_platform=True,
    )

    assert check_platform_domain(None) == []


def test_check_platform_domain__degrades_on_database_error(monkeypatch):
    def raise_database_error(*args, **kwargs):
        raise DatabaseError

    monkeypatch.setattr(DomainQuerySet, "get", raise_database_error)

    assert check_platform_domain(None) == []


def test_check_managed_domain_dns__requires_managed_zone(settings):
    settings.RELAY_MANAGED_SENDER_DOMAIN = ""
    errors = check_managed_domain_dns(None)

    assert [error.id for error in errors] == ["domains.E001"]


def test_check_managed_domain_dns__accepts_expected_nameservers(
    dns_resolver,
    settings,
):
    settings.RELAY_MANAGED_SENDER_DOMAIN = "open.example.com"
    settings.RELAY_DNS_NS_NAMESERVERS = ["ns1.example.com", "ns2.example.com"]
    dns_resolver.add(
        "open.example.com",
        "NS",
        "NS1.EXAMPLE.COM.",
        "ns2.example.com.",
    )

    assert check_managed_domain_dns(None) == []


def test_check_managed_domain_dns__reports_nameserver_mismatch(
    dns_resolver,
    settings,
):
    settings.RELAY_MANAGED_SENDER_DOMAIN = "open.example.com"
    settings.RELAY_DNS_NS_NAMESERVERS = ["ns1.example.com", "ns2.example.com"]
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
