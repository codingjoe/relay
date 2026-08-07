"""DNS record resolver. Build DNS records from Domain models."""

import base64
from collections.abc import Iterator

from django.conf import settings
from dnslib import CNAME, MX, NS, PTR, RR, TXT, A, DNSLabel
from dnslib.dns import QTYPE

from .models import Domain


def txt(value: str) -> TXT:
    """Create a TXT rdata. If a value is longer than 255 characters, split it into multiple strings."""
    if len(value) <= 255:
        return TXT(value)
    return TXT([value[i : i + 255] for i in range(0, len(value), 255)])


class DNSResolver:
    """Resolve DNS queries."""

    MX_PRIORITY: int = 10
    NS_TTL: int = 3600
    RECORD_TTL: int = 1800

    def resolve(self, qname: DNSLabel, qtype: int) -> list[RR]:
        """Resolve a DNS query and return a list of RR records."""
        query_name = str(qname).strip().rstrip(".").lower()
        match qtype:
            case QTYPE.PTR | QTYPE.ANY if query_name.endswith(".in-addr.arpa"):
                return self.resolve_ptr(qname, query_name)
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

        match qtype:
            case QTYPE.A | QTYPE.ANY:
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
                if not domain.is_managed and query_name == domain.name:
                    yield RR(
                        qname,
                        QTYPE.MX,
                        rdata=MX(domain.sender_domain, self.MX_PRIORITY),
                        ttl=self.RECORD_TTL,
                    )
            case QTYPE.TXT | QTYPE.ANY:
                yield from self.resolve_txt(qname, qtype, query_name, domain)
            case QTYPE.CNAME | QTYPE.ANY:
                yield from self.resolve_cname(qname, qtype, query_name, domain)
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
            case name if name == f"_smtp._tls.{domain.sender_domain}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.sender_tls_rpt_record),
                    ttl=self.RECORD_TTL,
                )

        # DKIM. Serve public-key for each cipher at its selector name.
        for selector, key in domain.dkim_ciphers:
            if key:
                public_key_b64 = base64.b64encode(key.public_bytes_der()).decode(
                    "ascii"
                )
                record = f"v=DKIM1; t=s; h=sha256; p={public_key_b64};"
                dkim_names = [f"{selector}._domainkey.{domain.sender_domain}"]
                if not domain.is_managed:
                    dkim_names.append(f"{selector}._domainkey.{domain.name}")
                if query_name in dkim_names:
                    yield RR(qname, QTYPE.TXT, rdata=txt(record), ttl=self.RECORD_TTL)

        # Extra records served only for org-owned (non-managed) domains
        if not domain.is_managed:
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
        qtype: int,
        query_name: str,
        domain: Domain,
    ) -> Iterator[RR]:
        """Build CNAME records for MTA-STS and Return-Path."""
        # MTA-STS CNAME served at sender subdomain and root domain.
        mta_sts_names = [f"mta-sts.{domain.sender_domain}"]
        if not domain.is_managed:
            mta_sts_names.append(f"mta-sts.{domain.name}")

        match query_name:
            case name if name in mta_sts_names:
                yield RR(
                    qname,
                    QTYPE.CNAME,
                    rdata=CNAME(DNSLabel(f"mta-sts.{settings.RELAY_PLATFORM_DOMAIN}")),
                    ttl=self.RECORD_TTL,
                )
            case name if name == domain.return_path_domain:
                yield RR(
                    qname,
                    QTYPE.CNAME,
                    rdata=CNAME(DNSLabel(settings.RELAY_DNS_RETURN_PATH_DOMAIN)),
                    ttl=self.RECORD_TTL,
                )

    def resolve_ptr(self, qname: DNSLabel, query_name: str) -> list[RR]:
        """Return PTR records for the sender subdomain of the queried SMTP IP."""
        smtp_ip_address = ".".join(
            reversed(query_name.removesuffix(".in-addr.arpa").split("."))
        )
        if smtp_ip_address not in settings.RELAY_DNS_SMTP_IPS:
            return []

        domain = Domain.objects.first()
        if domain is None:
            return []

        return [
            RR(
                qname,
                QTYPE.PTR,
                rdata=PTR(DNSLabel(domain.sender_domain)),
                ttl=self.RECORD_TTL,
            )
        ]
