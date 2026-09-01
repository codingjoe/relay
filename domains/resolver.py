"""Authoritative DNS resolver backed by Domain models."""

import base64
from collections.abc import Iterator

from django.conf import settings
from django.db import DatabaseError
from dnslib import CNAME, MX, NS, RR, TXT, A, DNSLabel, DNSRecord
from dnslib.dns import QTYPE, RCODE, DNSError
from dnslib.server import BaseResolver

from kms.models import SigningKey

from .models import Domain


def txt(value: str) -> TXT:
    """Create a TXT rdata. If a value is longer than 255 characters, split it into multiple strings."""
    if len(value) <= 255:
        return TXT(value)
    return TXT([value[i : i + 255] for i in range(0, len(value), 255)])


def dkim_record(key) -> str:
    """Render the DKIM public key record value for a signing key."""
    match key.algorithm:
        case SigningKey.Algorithm.ED25519:
            public_key_b64 = base64.b64encode(key.public_bytes_raw()).decode("ascii")
            return f"v=DKIM1; k=ed25519; t=s; h=sha256; p={public_key_b64};"
        case _:
            public_key_b64 = base64.b64encode(key.public_bytes_der()).decode("ascii")
            return f"v=DKIM1; k=rsa; t=s; h=sha256; p={public_key_b64};"


class DNSResolver(BaseResolver):
    """Resolve DNS queries."""

    MX_PRIORITY: int = 10
    NS_TTL: int = 3600
    RECORD_TTL: int = 1800

    def resolve(self, request: DNSRecord, handler) -> DNSRecord:
        """Return an authoritative DNS reply."""
        reply = request.reply(ra=0)

        try:
            reply.add_answer(*self.resolve_records(request.q.qname, request.q.qtype))
        except DNSError, DatabaseError:
            reply.header.rcode = RCODE.SERVFAIL

        return reply

    def resolve_records(self, qname: DNSLabel, qtype: int) -> list[RR]:
        """Return matching DNS records."""
        query_name = str(qname).strip().rstrip(".").lower()
        match qtype:
            case QTYPE.A | QTYPE.ANY if (
                query_name == settings.RELAY_SMTP_PUBLIC_HOSTNAME
            ):
                return [
                    RR(
                        qname,
                        QTYPE.A,
                        rdata=A(smtp_ip_address),
                        ttl=self.RECORD_TTL,
                    )
                    for smtp_ip_address in settings.RELAY_DNS_SMTP_IPS
                ]
            case _:
                try:
                    domain = Domain.objects.root_for(query_name, include_managed=True)
                except Domain.DoesNotExist:
                    return []
                return list(
                    self.resolve_domain_records(qname, qtype, query_name, domain)
                )

    def resolve_domain_records(
        self,
        qname: DNSLabel,
        qtype: int,
        query_name: str,
        domain: Domain,
    ) -> Iterator[RR]:
        """Build DNS records for a matched domain."""
        cname_records = list(self.resolve_cname(qname, query_name, domain))
        if cname_records:
            yield from cname_records
            return

        match qtype:
            case QTYPE.A | QTYPE.ANY if query_name == domain.sender_domain:
                for smtp_ip_address in settings.RELAY_DNS_SMTP_IPS:
                    yield RR(
                        qname, QTYPE.A, rdata=A(smtp_ip_address), ttl=self.RECORD_TTL
                    )
            case QTYPE.MX | QTYPE.ANY:
                yield RR(
                    qname,
                    QTYPE.MX,
                    rdata=MX(domain.sender_domain, self.MX_PRIORITY),
                    ttl=self.RECORD_TTL,
                )
            case QTYPE.TXT | QTYPE.ANY:
                yield from self.resolve_txt(qname, qtype, query_name, domain)
            case QTYPE.NS | QTYPE.ANY:
                for nameserver in settings.RELAY_DNS_NS_NAMESERVERS:
                    yield RR(
                        qname, QTYPE.NS, rdata=NS(DNSLabel(nameserver)), ttl=self.NS_TTL
                    )

    def resolve_txt(
        self,
        qname: DNSLabel,
        qtype: int,
        query_name: str,
        domain: Domain,
    ) -> Iterator[RR]:
        """Build TXT records for SPF, DKIM, DMARC, and TLS-RPT."""
        # Records served for all domains (managed and org-owned)
        match query_name:
            case name if name == domain.sender_domain:
                yield RR(
                    qname, QTYPE.TXT, rdata=txt(domain.spf_record), ttl=self.RECORD_TTL
                )
            case name if name == f"_dmarc.{domain.name}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.dmarc_record),
                    ttl=self.RECORD_TTL,
                )
            case name if name == f"_mta-sts.{domain.name}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.mta_sts_record),
                    ttl=self.RECORD_TTL,
                )
            case name if name == f"_smtp._tls.{domain.sender_domain}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.tls_rpt_record),
                    ttl=self.RECORD_TTL,
                )

        yield from self.resolve_dkim_txt(qname, query_name, domain)
        yield from self.resolve_apex_txt(qname, query_name, domain)

    def resolve_dkim_txt(
        self,
        qname: DNSLabel,
        query_name: str,
        domain: Domain,
    ) -> Iterator[RR]:
        """Build DKIM TXT records. Serve each cipher's public key at its selector."""
        for selector, key in domain.dkim_ciphers:
            if key:
                dkim_names = [
                    f"{selector}._domainkey.{domain.sender_domain}",
                    f"{selector}._domainkey.{domain.name}",
                ]
                if query_name in dkim_names:
                    yield RR(
                        qname,
                        QTYPE.TXT,
                        rdata=txt(dkim_record(key)),
                        ttl=self.RECORD_TTL,
                    )

    def resolve_apex_txt(
        self,
        qname: DNSLabel,
        query_name: str,
        domain: Domain,
    ) -> Iterator[RR]:
        """Build TXT records served at the domain apex."""
        match query_name:
            case name if name == domain.name:
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.root_spf_record),
                    ttl=self.RECORD_TTL,
                )
            case name if name == f"_dmarc.{domain.sender_domain}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.sender_dmarc_record),
                    ttl=self.RECORD_TTL,
                )
            case name if name == f"_smtp._tls.{domain.name}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.tls_rpt_record),
                    ttl=self.RECORD_TTL,
                )

    def resolve_cname(
        self,
        qname: DNSLabel,
        query_name: str,
        domain: Domain,
    ) -> Iterator[RR]:
        """Build CNAME records for MTA-STS."""
        match query_name:
            case name if name == f"mta-sts.{domain.name}":
                target = f"mta-sts.{domain.sender_domain}"
            case name if name == f"mta-sts.{domain.sender_domain}":
                target = f"mta-sts.{settings.RELAY_PLATFORM_DOMAIN}"
            case _:
                return

        yield RR(
            qname,
            QTYPE.CNAME,
            rdata=CNAME(DNSLabel(target)),
            ttl=self.RECORD_TTL,
        )
