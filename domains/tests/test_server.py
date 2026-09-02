import base64
import re
from unittest.mock import patch

import pytest
from django.db import DatabaseError
from dnslib import RCODE, DNSLabel, DNSRecord
from dnslib.dns import QTYPE, DNSError

from accounts.models import Organization
from domains.models import Domain
from domains.resolver import DNSResolver
from kms import keys as kms_keys
from kms.models import SigningKey


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

    def test_resolve__dns_error(self, django_db_blocker):
        resolver = DNSResolver()
        with (
            django_db_blocker.unblock(),
            patch.object(
                resolver,
                "resolve_records",
                side_effect=DNSError("Invalid DNS record"),
            ),
        ):
            reply = resolver.resolve(DNSRecord.question("example.com"), None)

        assert reply.header.rcode == RCODE.SERVFAIL
        assert reply.rr == []

    def test_resolve__database_error(self, django_db_blocker):
        resolver = DNSResolver()
        with (
            django_db_blocker.unblock(),
            patch.object(
                resolver,
                "resolve_records",
                side_effect=DatabaseError("Database unavailable"),
            ),
        ):
            reply = resolver.resolve(DNSRecord.question("example.com"), None)

        assert reply.header.rcode == RCODE.SERVFAIL
        assert reply.rr == []


def make_domain_with_dkim_key(algorithm):
    """Create an unsaved Domain with a single DKIM signing key."""
    pair = kms_keys.generate(algorithm)
    key = SigningKey(
        algorithm=algorithm,
        encrypted_private_key=pair.ciphertext,
        public_key=pair.public_key_pem,
        key_id=pair.key_id,
    )
    domain = Domain(name="example.com")
    match algorithm:
        case SigningKey.Algorithm.ED25519:
            domain.dkim_key_ed25519 = key
        case SigningKey.Algorithm.RSA_2048:
            domain.dkim_key_rsa2048 = key
    return domain


class TestResolveTxt:
    def test_resolve_txt__ed25519_dkim_record_includes_k_tag(self):
        domain = make_domain_with_dkim_key(SigningKey.Algorithm.ED25519)
        selector, _ = domain.dkim_ciphers[1]
        query_name = f"{selector}._domainkey.{domain.name}"
        records = list(
            DNSResolver().resolve_txt(
                DNSLabel(query_name), QTYPE.TXT, query_name, domain
            )
        )
        record_str = b"".join(records[0].rdata.data).decode("ascii")
        assert "k=ed25519" in record_str

    def test_resolve_txt__ed25519_dkim_record_has_raw_public_key(self):
        domain = make_domain_with_dkim_key(SigningKey.Algorithm.ED25519)
        selector, _ = domain.dkim_ciphers[1]
        query_name = f"{selector}._domainkey.{domain.name}"
        records = list(
            DNSResolver().resolve_txt(
                DNSLabel(query_name), QTYPE.TXT, query_name, domain
            )
        )
        record_str = b"".join(records[0].rdata.data).decode("ascii")
        match = re.search(r"p=([^;]+)", record_str)
        public_key = base64.b64decode(match.group(1))
        assert len(public_key) == 32

    def test_resolve_txt__rsa_dkim_record_includes_k_tag(self):
        domain = make_domain_with_dkim_key(SigningKey.Algorithm.RSA_2048)
        selector, _ = domain.dkim_ciphers[0]
        query_name = f"{selector}._domainkey.{domain.name}"
        records = list(
            DNSResolver().resolve_txt(
                DNSLabel(query_name), QTYPE.TXT, query_name, domain
            )
        )
        record_str = b"".join(records[0].rdata.data).decode("ascii")
        assert "k=rsa" in record_str

    def test_resolve_txt__rsa_dkim_record_has_der_public_key(self):
        domain = make_domain_with_dkim_key(SigningKey.Algorithm.RSA_2048)
        selector, _ = domain.dkim_ciphers[0]
        query_name = f"{selector}._domainkey.{domain.name}"
        records = list(
            DNSResolver().resolve_txt(
                DNSLabel(query_name), QTYPE.TXT, query_name, domain
            )
        )
        record_str = b"".join(records[0].rdata.data).decode("ascii")
        match = re.search(r"p=([^;]+)", record_str)
        public_key = base64.b64decode(match.group(1))
        assert public_key[:2] == b"\x30\x82"
