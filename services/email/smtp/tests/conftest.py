import dns.resolver
import pytest

from domains.tests.conftest import StubResolver


@pytest.fixture
def dns_resolver():
    """Replace the default DNS resolver with a configurable stub."""
    stub = StubResolver()
    original = dns.resolver.default_resolver
    dns.resolver.default_resolver = stub
    try:
        yield stub
    finally:
        dns.resolver.default_resolver = original
