"""DNS record resolver: build DNS records from Domain models."""

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
        qname_str = str(qname).rstrip(".")
        match qtype.upper():
            case "PTR" | "ANY" if qname_str.endswith(".in-addr.arpa"):
                return self.resolve_ptr(qname, qname_str)
            case _:
                domain = self.find_domain(qname_str)
                if domain is None:
                    return []
                return self.resolve_domain_records(qname, qtype, qname_str, domain)

    def resolve_domain_records(self, qname, qtype, qname_str, domain):
        """Build DNS records for a matched domain."""
        base = domain.name if domain.is_system else domain.sender_domain
        records = []

        match qtype.upper():
            case "A" | "ANY":
                for ip in settings.RELAY_DNS_SMTP_IPS:
                    records.append(RR(qname, QTYPE.A, rdata=A(ip), ttl=self.RECORD_TTL))
            case "MX" | "ANY":
                records.append(
                    RR(
                        qname,
                        QTYPE.MX,
                        rdata=MX(base, self.MX_PRIORITY),
                        ttl=self.RECORD_TTL,
                    )
                )
            case "TXT" | "ANY":
                records.extend(self.resolve_txt(qname, qname_str, base, domain))
            case "CNAME" | "ANY":
                if qname_str.lower() == f"mta-sts.{base}".rstrip(".").lower():
                    records.append(
                        RR(
                            qname,
                            QTYPE.CNAME,
                            rdata=CNAME(
                                DNSLabel(f"mta-sts.{settings.RELAY_PLATFORM_DOMAIN}")
                            ),
                            ttl=self.RECORD_TTL,
                        )
                    )
                rp_name = domain.return_path_domain
                if qname_str.lower() == rp_name.rstrip(".").lower():
                    records.append(
                        RR(
                            qname,
                            QTYPE.CNAME,
                            rdata=CNAME(
                                DNSLabel(settings.RELAY_DNS_RETURN_PATH_DOMAIN)
                            ),
                            ttl=self.RECORD_TTL,
                        )
                    )
            case "NS" | "ANY":
                for ns in settings.RELAY_DNS_NS_NAMESERVERS:
                    records.append(
                        RR(qname, QTYPE.NS, rdata=NS(DNSLabel(ns)), ttl=self.NS_TTL)
                    )

        return records

    def resolve_txt(self, qname, qname_str, base, domain):
        """Build TXT records for SPF, DKIM, verification, DMARC, and TLS-RPT."""
        records = []
        qname_lower = qname_str.lower()

        if qname_lower == base.lower():
            records.append(
                RR(qname, QTYPE.TXT, rdata=txt(domain.spf_record), ttl=self.RECORD_TTL)
            )

        # DKIM: serve public key for each cipher at its selector name
        for selector, key in domain.dkim_ciphers:
            if key:
                key_record_name = f"{selector}._domainkey.{base}"
                if qname_lower == key_record_name.rstrip(".").lower():
                    p = base64.b64encode(key.public_bytes_der()).decode("ascii")
                    record = f"v=DKIM1; t=s; h=sha256; p={p};"
                    records.append(
                        RR(qname, QTYPE.TXT, rdata=txt(record), ttl=self.RECORD_TTL)
                    )

        verify_name = domain.verification_record_name
        if qname_lower == verify_name.rstrip(".").lower():
            records.append(
                RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.verification_record),
                    ttl=self.RECORD_TTL,
                )
            )

        # DMARC: system domains serve at the apex, user domains serve at the
        # sender subdomain for external reporting authorization.
        if domain.is_system and qname_lower == f"_dmarc.{domain.name}".lower():
            records.append(
                RR(qname, QTYPE.TXT, rdata=txt("v=DMARC1; p=none"), ttl=self.RECORD_TTL)
            )
        if not domain.is_system and qname_lower == f"_dmarc.{base}".lower():
            records.append(
                RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.sender_dmarc_record),
                    ttl=self.RECORD_TTL,
                )
            )

        # TLS-RPT: served at _smtp._tls.{base} for all domains.
        if qname_lower == f"_smtp._tls.{base}".lower():
            records.append(
                RR(
                    qname,
                    QTYPE.TXT,
                    rdata=txt(domain.sender_tls_rpt_record),
                    ttl=self.RECORD_TTL,
                )
            )

        return records

    def find_domain(self, qname_str):
        """Return the Domain whose zone owns a query name, or None."""
        for domain in Domain.objects.filter(org=None):
            name = domain.name.lower()
            if qname_str.lower() == name or qname_str.lower().endswith(f".{name}"):
                return domain

        prefix_labels = settings.RELAY_SENDER_SUBDOMAIN_PREFIX.lower().split(".")
        parts = qname_str.split(".")

        for i in range(len(parts) - len(prefix_labels) + 1):
            if [p.lower() for p in parts[i : i + len(prefix_labels)]] == prefix_labels:
                if root := ".".join(parts[i + len(prefix_labels) :]):
                    return Domain.objects.filter(name__iexact=root).first()
                break

        return None

    def resolve_ptr(self, qname, qname_str):
        """Return PTR records for the sender subdomain of the queried SMTP IP."""
        ip = ".".join(reversed(qname_str.removesuffix(".in-addr.arpa").split(".")))
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
