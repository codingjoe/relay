from unittest.mock import patch

import pytest
from django.db import DatabaseError
from dnslib import RCODE, DNSRecord
from dnslib.dns import DNSError

from accounts.models import Organization
from domains.models import Domain
from domains.resolver import DNSResolver


class TestResolve:
    @pytest.mark.django_db
    def test_resolve__unknown_domain(self):
        reply = DNSResolver().resolve(DNSRecord.question("unknown.com"), None)

        assert reply.header.rcode == RCODE.NOERROR
        assert reply.header.aa == 1
        assert reply.header.ra == 0
        assert reply.rr == []

    @pytest.mark.django_db
    def test_resolve__known_domain(self):
        organization = Organization.objects.create(slug="dns-server")
        domain = Domain.objects.create(name="example.com", org=organization)

        reply = DNSResolver().resolve(DNSRecord.question(domain.sender_domain), None)

        assert reply.header.rcode == RCODE.NOERROR
        assert reply.header.aa == 1
        assert reply.header.ra == 0
        assert reply.rr

    def test_resolve__dns_error(self):
        resolver = DNSResolver()
        with patch.object(
            resolver,
            "resolve_records",
            side_effect=DNSError("Invalid DNS record"),
        ):
            reply = resolver.resolve(DNSRecord.question("example.com"), None)

        assert reply.header.rcode == RCODE.SERVFAIL
        assert reply.rr == []

    def test_resolve__database_error(self):
        resolver = DNSResolver()
        with patch.object(
            resolver,
            "resolve_records",
            side_effect=DatabaseError("Database unavailable"),
        ):
            reply = resolver.resolve(DNSRecord.question("example.com"), None)

        assert reply.header.rcode == RCODE.SERVFAIL
        assert reply.rr == []
