"""DNS record resolver. Build DNS records from Domain models."""

import base64

from django.conf import settings
from dnslib import CNAME, MX, NS, PTR, RR, TXT, A, DNSLabel
from dnslib.dns import QTYPE

from .models import Domain


def txt(value):
    """Create a TXT rdata. If a value is longer than 255 characters, split it into multiple strings."""
    if len(value) <= 255:
        return TXT(value)
    return TXT([value[i : i + 255] for i in range(0, len(value), 255)])


class DNSResolver:
    """Resolve DNS queries."""

    MX_PRIORITY = 10
    NS_TTL = 3600
    RECORD_TTL = 1800

    def __init__(self):
        pass

    def resolve(self, qname, qtype):
        """Resolve a DNS query and return a list of RR records."""
        cleaned_qname = str(qname).strip().rstrip(".").lower()
        match qtype.upper():
            case "PTR" | "ANY" if cleaned_qname.endswith(".in-addr.arpa"):
                return self.resolve_ptr(qname, cleaned_qname)
            case _:
                try:
                    domain = Domain.objects.root_for(
                        cleaned_qname, include_managed=True
                    )
                except Domain.DoesNotExist:
                    return []
                return list(
                    self.resolve_domain_records(qname, qtype, cleaned_qname, domain)
                )

    def resolve_domain_records(self, qname, qtype, cleaned_qname, domain):
        """Build DNS records for a matched domain."""
        base = domain.name if domain.is_system else domain.sender_domain

        match qtype.upper():
            case "A" | "ANY":
                for ip in settings.RELAY_DNS_SMTP_IPS:
                    yield RR(qname, QTYPE.A, rdata=A(ip), ttl=self.RECORD_TTL)
            case "MX" | "ANY":
                yield RR(
                    qname,
                    QTYPE.MX,
                    rdata=MX(base, self.MX_PRIORITY),
                    ttl=self.RECORD_TTL,
                )
                if not domain.is_system and cleaned_qname == domain.name:
                    yield RR(
                        qname,
                        QTYPE.MX,
                        rdata=MX(domain.sender_domain, self.MX_PRIORITY),
                        ttl=self.RECORD_TTL,
                    )
            case "TXT" | "ANY":
                yield from self.resolve_txt(qname, qtype, cleaned_qname, base, domain)
            case "CNAME" | "ANY":
                yield from self.resolve_cname(qname, qtype, cleaned_qname, base, domain)
            case "NS" | "ANY":
                for ns in settings.RELAY_DNS_NS_NAMESERVERS:
                    yield RR(qname, QTYPE.NS, rdata=NS(DNSLabel(ns)), ttl=self.NS_TTL)

    def resolve_txt(self, qname, qtype, cleaned_qname, base, domain):
        """Build TXT records for SPF, DKIM, verification, DMARC, and TLS-RPT."""
        # Records served for all domains (system and org-owned)
        match cleaned_qname:
            case c if c == base:
                yield RR(
                    qname, QTYPE.TXT, rdata=txt(domain.spf_record), ttl=self.RECORD_TTL
                )
            case c if c == domain.verification_record_name:
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.verification_record),
                    ttl=self.RECORD_TTL,
                )
            case c if c == f"_smtp._tls.{base}":
                yield RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.sender_tls_rpt_record),
                    ttl=self.RECORD_TTL,
                )

        # DKIM. Serve public-key for each cipher at its selector name.
        for selector, key in domain.dkim_ciphers:
            if key:
                p = base64.b64encode(key.public_bytes_der()).decode("ascii")
                record = f"v=DKIM1; t=s; h=sha256; p={p};"
                dkim_names = [f"{selector}._domainkey.{base}"]
                if not domain.is_system:
                    dkim_names.append(f"{selector}._domainkey.{domain.name}")
                if cleaned_qname in dkim_names:
                    yield RR(qname, QTYPE.TXT, rdata=txt(record), ttl=self.RECORD_TTL)

        if domain.is_system:
            match cleaned_qname:
                case c if c == f"_dmarc.{domain.name}":
                    yield RR(
                        qname,
                        QTYPE.TXT,
                        rdata=txt("v=DMARC1; p=none"),
                        ttl=self.RECORD_TTL,
                    )
        else:
            match cleaned_qname:
                case c if c == domain.name:
                    yield RR(
                        qname,
                        QTYPE.TXT,
                        rdata=txt(domain.root_spf_record),
                        ttl=self.RECORD_TTL,
                    )
                case c if c == f"_dmarc.{base}":
                    yield RR(
                        qname,
                        QTYPE.TXT,
                        rdata=txt(domain.sender_dmarc_record),
                        ttl=self.RECORD_TTL,
                    )
                case c if c == f"_dmarc.{domain.name}":
                    yield RR(
                        qname,
                        QTYPE.TXT,
                        rdata=txt(domain.dmarc_record),
                        ttl=self.RECORD_TTL,
                    )
                case c if c == f"_smtp._tls.{domain.name}":
                    yield RR(
                        qname,
                        QTYPE.TXT,
                        rdata=txt(domain.tls_rpt_record),
                        ttl=self.RECORD_TTL,
                    )

    def resolve_cname(self, qname, qtype, cleaned_qname, base, domain):
        """Build CNAME records for MTA-STS and Return-Path."""
        # MTA-STS CNAME served at sender subdomain and root domain.
        mta_sts_names = [f"mta-sts.{base}"]
        if not domain.is_system:
            mta_sts_names.append(f"mta-sts.{domain.name}")

        match cleaned_qname:
            case c if c in mta_sts_names:
                yield RR(
                    qname,
                    QTYPE.CNAME,
                    rdata=CNAME(DNSLabel(f"mta-sts.{settings.RELAY_PLATFORM_DOMAIN}")),
                    ttl=self.RECORD_TTL,
                )
            case c if c == domain.return_path_domain:
                yield RR(
                    qname,
                    QTYPE.CNAME,
                    rdata=CNAME(DNSLabel(settings.RELAY_DNS_RETURN_PATH_DOMAIN)),
                    ttl=self.RECORD_TTL,
                )

    def resolve_ptr(self, qname, cleaned_qname):
        """Return PTR records for the sender subdomain of the queried SMTP IP."""
        ip = ".".join(reversed(cleaned_qname.removesuffix(".in-addr.arpa").split(".")))
        if ip not in settings.RELAY_DNS_SMTP_IPS:
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
