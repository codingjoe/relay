from types import SimpleNamespace

from django.core.cache import cache

from abstract.hostnames import (
    add_sender_hostname,
    is_relay_address,
    lookup_sender_hostname,
    resolve_hostname,
)


class TestResolveHostname:
    def test_resolve_hostname__returns_ptr_hostname(self, dns_resolver):
        dns_resolver.add("8.8.8.8.in-addr.arpa", "PTR", "dns.google.")
        assert resolve_hostname("8.8.8.8") == "dns.google"

    def test_resolve_hostname__returns_empty_string_without_ptr(self, dns_resolver):
        assert resolve_hostname("8.8.8.8") == ""

    def test_resolve_hostname__skips_private_addresses(self, dns_resolver):
        assert resolve_hostname("10.244.0.1") == ""
        assert dns_resolver.lookups == []

    def test_resolve_hostname__skips_malformed_addresses(self, dns_resolver):
        assert resolve_hostname("not-an-ip") == ""
        assert dns_resolver.lookups == []


class TestIsRelayAddress:
    def test_is_relay_address__true_for_smtp_source_ip(self, settings):
        settings.SMTP_SOURCE_IPS = ["8.8.8.8"]
        settings.DNS_SMTP_IPS = []
        assert is_relay_address("8.8.8.8")

    def test_is_relay_address__true_for_dns_published_ip(self, settings):
        settings.SMTP_SOURCE_IPS = []
        settings.DNS_SMTP_IPS = ["8.8.8.8"]
        assert is_relay_address("8.8.8.8")

    def test_is_relay_address__false_for_other_ip(self, settings):
        settings.SMTP_SOURCE_IPS = ["8.8.8.8"]
        settings.DNS_SMTP_IPS = ["8.8.8.8"]
        assert not is_relay_address("1.1.1.1")


class TestLookupSenderHostname:
    def test_lookup_sender_hostname__returns_ptr_hostname(self, dns_resolver):
        cache.delete("relay:sender-hostname:8.8.8.8")
        dns_resolver.add("8.8.8.8.in-addr.arpa", "PTR", "sender-1.mail.example.org.")
        assert lookup_sender_hostname("8.8.8.8") == "sender-1.mail.example.org"

    def test_lookup_sender_hostname__caches_lookup(self, dns_resolver):
        cache.delete("relay:sender-hostname:8.8.8.8")
        dns_resolver.add("8.8.8.8.in-addr.arpa", "PTR", "sender-1.mail.example.org.")
        lookup_sender_hostname("8.8.8.8")
        lookup_sender_hostname("8.8.8.8")
        assert dns_resolver.lookups == [("8.8.8.8.in-addr.arpa", "PTR")]


class TestAddSenderHostname:
    def test_add_sender_hostname__attaches_hostname(self, settings, dns_resolver):
        cache.delete("relay:sender-hostname:8.8.8.8")
        settings.SMTP_SOURCE_IPS = ["8.8.8.8"]
        dns_resolver.add("8.8.8.8.in-addr.arpa", "PTR", "sender-1.mail.example.org.")
        report = SimpleNamespace()
        add_sender_hostname(report, "8.8.8.8")
        assert report.sender_hostname == "sender-1.mail.example.org"

    def test_add_sender_hostname__skips_other_address(self, settings):
        settings.SMTP_SOURCE_IPS = ["8.8.8.8"]
        report = SimpleNamespace()
        add_sender_hostname(report, "1.1.1.1")
        assert not hasattr(report, "sender_hostname")
