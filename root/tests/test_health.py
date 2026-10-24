import types
from datetime import timedelta

import dns.exception
import dns.resolver
import pytest
from django.test import RequestFactory
from django.urls import reverse
from health_check.base import HealthCheck
from health_check.exceptions import ServiceUnavailable, ServiceWarning

from root.health import (
    BlocklistAddressError,
    BlocklistListing,
    BlocklistLookupError,
    BlocklistProvider,
    BlocklistRefusal,
    BlocklistWarning,
    CachedHealthCheckView,
    DnsBlocklist,
    ReputationHealthCheckView,
)

PROVIDER = BlocklistProvider(
    "Example",
    "example.test",
    frozendict({"127.0.0.2": "listed"}),
)


class FakeResolver:
    def __init__(self, answers=(), error=None):
        self.answers = answers
        self.error = error

    async def resolve(self, query, record_type):
        if self.error:
            raise self.error
        return self.answers


class RecordingResolver:
    def __init__(self, answers=()):
        self.answers = answers
        self.queries = []

    async def resolve(self, query, record_type):
        self.queries.append(query)
        return self.answers


class DummyResolver:
    async def resolve(self, query, record_type):
        raise AssertionError


class PassingCheck(HealthCheck):
    async def run(self):
        return None


class WarningCheck(HealthCheck):
    async def run(self):
        raise ServiceWarning("warned")


class UnavailableCheck(HealthCheck):
    async def run(self):
        raise ServiceUnavailable("unavailable")


class BrokenCheck(HealthCheck):
    async def run(self):
        raise ValueError("broken")


class TestBlocklistProvider:
    def test_reasons__defaults_to_a_frozen_empty_mapping(self):
        provider = BlocklistProvider("Example", "example.test")
        assert isinstance(provider.reasons, frozendict)
        assert not provider.reasons


class TestBlocklistListing:
    def test_init__with_reason(self):
        error = BlocklistListing("192.0.2.1", PROVIDER, ["127.0.0.2"])
        assert error.message == "Listed on Example (example.test): listed"

    def test_init__without_reason(self):
        error = BlocklistListing("192.0.2.1", PROVIDER, ["127.0.0.9"])
        assert error.message == "Listed on Example (example.test)"


class TestBlocklistLookupError:
    def test_init__names_the_exception_class_only(self):
        error = BlocklistLookupError(
            "192.0.2.1",
            PROVIDER,
            ValueError("resolver 10.0.0.53"),
        )
        assert error.message == "Example (example.test) lookup failed: ValueError"

    def test_init__explains_a_timeout(self):
        error = BlocklistLookupError(
            "192.0.2.1",
            PROVIDER,
            dns.resolver.LifetimeTimeout(5.0, []),
        )
        assert (
            error.message
            == "Example (example.test) lookup failed: the provider did not answer "
            "in time"
        )

    def test_init__explains_missing_nameservers(self):
        """Skip the request dnspython would format the message from."""
        error = dns.resolver.NoNameservers.__new__(dns.resolver.NoNameservers)
        assert (
            BlocklistLookupError("192.0.2.1", PROVIDER, error).message
            == "Example (example.test) lookup failed: no nameserver answered for "
            "the provider"
        )


class TestBlocklistRefusal:
    def test_init__translates_a_known_code(self):
        error = BlocklistRefusal(
            "192.0.2.1",
            PROVIDER,
            ["127.255.255.253"],
        )
        assert (
            error.message
            == "Example (example.test) refused the lookup: the provider rejected "
            "the query from this resolver"
        )

    def test_init__falls_back_to_the_resolver_hint(self):
        error = BlocklistRefusal(
            "192.0.2.1",
            PROVIDER,
            ["127.255.255.1"],
        )
        assert "check the DNS resolver configuration" in error.message


class TestBlocklistAddressError:
    def test_init__names_the_address(self):
        error = BlocklistAddressError("not-an-ip")
        assert error.message == "not-an-ip is not an IP address"


class TestDnsBlocklistLookup:
    async def test_lookup__ignores_nxdomain(self):
        check = DnsBlocklist(address="192.0.2.1")
        error = dns.resolver.NXDOMAIN()
        issue = await check.lookup(PROVIDER, "1.2.0.192", FakeResolver(error=error))
        assert issue is None

    async def test_lookup__ignores_no_answer(self):
        check = DnsBlocklist(address="192.0.2.1")
        error = dns.resolver.NoAnswer()
        issue = await check.lookup(PROVIDER, "1.2.0.192", FakeResolver(error=error))
        assert issue is None

    async def test_lookup__returns_a_lookup_error(self):
        check = DnsBlocklist(address="192.0.2.1")
        error = dns.exception.DNSException("boom")
        issue = await check.lookup(PROVIDER, "1.2.0.192", FakeResolver(error=error))
        assert isinstance(issue, BlocklistLookupError)
        assert issue.message == "Example (example.test) lookup failed: DNSException"

    async def test_lookup__returns_a_refusal(self):
        check = DnsBlocklist(address="192.0.2.1")
        resolver = FakeResolver(
            answers=[types.SimpleNamespace(address="127.255.255.253")]
        )
        issue = await check.lookup(PROVIDER, "1.2.0.192", resolver)
        assert isinstance(issue, BlocklistRefusal)
        assert "the provider rejected the query from this resolver" in issue.message

    async def test_lookup__returns_a_listing(self):
        check = DnsBlocklist(address="192.0.2.1")
        resolver = FakeResolver(answers=[types.SimpleNamespace(address="127.0.0.2")])
        issue = await check.lookup(PROVIDER, "1.2.0.192", resolver)
        assert isinstance(issue, BlocklistListing)
        assert issue.message == "Listed on Example (example.test): listed"

    async def test_lookup__returns_a_listing_without_a_reason(self):
        check = DnsBlocklist(address="192.0.2.1")
        resolver = FakeResolver(answers=[types.SimpleNamespace(address="127.0.0.9")])
        issue = await check.lookup(PROVIDER, "1.2.0.192", resolver)
        assert isinstance(issue, BlocklistListing)
        assert issue.message == "Listed on Example (example.test)"


class TestDnsBlocklistSpamhausKey:
    provider = BlocklistProvider(
        "Spamhaus ZEN",
        "zen.dq.spamhaus.net",
        frozendict({"127.0.0.2": "SBL, spam source"}),
        keyed_zone="{key}.zen.dq.spamhaus.net",
    )

    async def test_lookup__queries_the_keyed_zone(self, settings):
        settings.SPAMHAUS_KEY = "key123"
        resolver = RecordingResolver()
        await DnsBlocklist(address="192.0.2.1").lookup(
            self.provider, "1.2.0.192", resolver
        )
        assert resolver.queries == ["1.2.0.192.key123.zen.dq.spamhaus.net"]

    async def test_lookup__queries_the_plain_zone_without_a_key(self, settings):
        settings.SPAMHAUS_KEY = ""
        resolver = RecordingResolver()
        await DnsBlocklist(address="192.0.2.1").lookup(
            self.provider, "1.2.0.192", resolver
        )
        assert resolver.queries == ["1.2.0.192.zen.dq.spamhaus.net"]

    async def test_lookup__keeps_the_key_out_of_a_listing(self, settings):
        settings.SPAMHAUS_KEY = "key123"
        resolver = RecordingResolver(
            answers=[types.SimpleNamespace(address="127.0.0.2")]
        )
        issue = await DnsBlocklist(address="192.0.2.1").lookup(
            self.provider, "1.2.0.192", resolver
        )
        assert "key123" not in issue.message
        assert issue.message == (
            "Listed on Spamhaus ZEN (zen.dq.spamhaus.net): SBL, spam source"
        )


class TestDnsBlocklistRun:
    async def test_run__raises_for_a_non_ip_address(self):
        check = DnsBlocklist(address="not-an-ip")
        with pytest.raises(BlocklistAddressError):
            await check.run()

    async def test_run__passes_when_every_lookup_is_clean(self, monkeypatch):
        check = DnsBlocklist(address="192.0.2.1", providers=(PROVIDER,))

        async def lookup(provider, reversed_address, resolver):
            return None

        monkeypatch.setattr(check, "lookup", lookup)
        await check.run()

    async def test_run__raises_unavailable_for_a_listing(self, monkeypatch):
        check = DnsBlocklist(address="192.0.2.1", providers=(PROVIDER,))

        async def lookup(provider, reversed_address, resolver):
            return BlocklistListing(check.address, provider, ["127.0.0.2"])

        monkeypatch.setattr(check, "lookup", lookup)
        monkeypatch.setattr(
            "root.health.dns.asyncresolver.Resolver",
            DummyResolver,
        )
        with pytest.raises(ServiceUnavailable) as exc_info:
            await check.run()
        assert "Listed on Example (example.test)" in exc_info.value.message

    async def test_run__raises_warning_for_a_lookup_error(self, monkeypatch):
        check = DnsBlocklist(address="192.0.2.1", providers=(PROVIDER,))

        async def lookup(provider, reversed_address, resolver):
            return BlocklistLookupError(check.address, provider, ValueError("boom"))

        monkeypatch.setattr(check, "lookup", lookup)
        monkeypatch.setattr(
            "root.health.dns.asyncresolver.Resolver",
            DummyResolver,
        )
        with pytest.raises(BlocklistWarning) as exc_info:
            await check.run()
        assert "lookup failed: ValueError" in exc_info.value.message

    async def test_run__joins_every_issue(self, monkeypatch):
        other = BlocklistProvider("Other", "other.test")
        check = DnsBlocklist(
            address="192.0.2.1",
            providers=(PROVIDER, other),
        )

        async def lookup(provider, reversed_address, resolver):
            if provider.name == "Example":
                return BlocklistListing(check.address, provider, ["127.0.0.2"])
            return BlocklistLookupError(check.address, provider, ValueError("boom"))

        monkeypatch.setattr(check, "lookup", lookup)
        monkeypatch.setattr(
            "root.health.dns.asyncresolver.Resolver",
            DummyResolver,
        )
        with pytest.raises(ServiceUnavailable) as exc_info:
            await check.run()
        assert "Listed on Example (example.test)" in exc_info.value.message
        assert "Other (other.test) lookup failed" in exc_info.value.message
        assert "\n" in exc_info.value.message


class TestCachedHealthCheckView:
    async def test_get__caches_a_failed_response(self):
        view = CachedHealthCheckView.as_view(
            checks=[UnavailableCheck],
            max_age=timedelta(seconds=30),
        )
        response = await view(RequestFactory().get("/health/application/"))
        assert response.status_code == 500
        assert response.headers["Cache-Control"] == "public, max-age=30"

    async def test_get__answers_no_store_without_max_age(self):
        view = CachedHealthCheckView.as_view(checks=[PassingCheck])
        response = await view(RequestFactory().get("/health/node/"))
        assert response.headers["Cache-Control"] == "no-store"


class TestReputationHealthCheckView:
    async def test_get__answers_200_when_every_check_passes(self):
        view = ReputationHealthCheckView.as_view(checks=[PassingCheck])
        response = await view(RequestFactory().get("/health/reputation/"))
        assert response.status_code == 200

    async def test_get__answers_200_for_a_warning(self):
        view = ReputationHealthCheckView.as_view(checks=[WarningCheck])
        response = await view(RequestFactory().get("/health/reputation/"))
        assert response.status_code == 200

    async def test_get__answers_500_for_an_unavailable(self):
        view = ReputationHealthCheckView.as_view(checks=[UnavailableCheck])
        response = await view(RequestFactory().get("/health/reputation/"))
        assert response.status_code == 500

    async def test_get__answers_500_for_an_unexpected_error(self):
        view = ReputationHealthCheckView.as_view(checks=[BrokenCheck])
        response = await view(RequestFactory().get("/health/reputation/"))
        assert response.status_code == 500


def test_reverse__health_reputation():
    assert reverse("health-reputation") == "/health/reputation/"
