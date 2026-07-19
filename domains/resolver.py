"""DNS record resolver — build DNS records from Domain models.

qtype dispatch uses match/case for readability (see CONVENTIONS.md).
"""

from django.conf import settings
from dnslib import A, CNAME, DNSLabel, MX, NS, PTR, RR, TXT
from dnslib.dns import QTYPE

from .models import Domain


def txt(value):
    """Create a TXT rdata, splitting values >255 chars into multiple strings."""
    if len(value) <= 255:
        return TXT(value)
    return TXT([value[i : i + 255] for i in range(0, len(value), 255)])


class DNSResolver:
    """Resolve DNS queries against the database."""

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
        # System domains serve at apex; user domains at sender subdomain
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
        """Build TXT records for SPF, DKIM, verification, and DMARC."""
        records = []
        qname_lower = qname_str.lower()

        if qname_lower == base.lower():
            records.append(
                RR(qname, QTYPE.TXT, rdata=txt(domain.spf_record), ttl=self.RECORD_TTL)
            )

        dkim_name = domain.dkim_record_name
        if qname_lower == dkim_name.rstrip(".").lower():
            records.append(
                RR(qname, QTYPE.TXT, rdata=txt(domain.dkim_record), ttl=self.RECORD_TTL)
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

        # DMARC for system domains (user domains set DMARC on their root)
        if domain.is_system and qname_lower == f"_dmarc.{domain.name}".lower():
            records.append(
                RR(qname, QTYPE.TXT, rdata=txt("v=DMARC1; p=none"), ttl=self.RECORD_TTL)
            )

        return records

    def find_domain(self, qname_str):
        """Return the Domain whose zone owns a query name, or None.

        System domains (org=None) match at the apex; user domains match via
        their fixed sender subdomain prefix (e.g. ``mail.example.com``).
        For DKIM alignment the user adds a CNAME on the root domain pointing
        into this zone, so the query still arrives here.
        """
        # System domains: match by domain name suffix
        for domain in Domain.objects.filter(org=None):
            name = domain.name.lower()
            if qname_str.lower() == name or qname_str.lower().endswith(f".{name}"):
                return domain

        # User domains: match by sender subdomain prefix
        prefix = settings.RELAY_SENDER_SUBDOMAIN_PREFIX.lower()
        parts = qname_str.split(".")

        for i, part in enumerate(parts):
            if part.lower() == prefix:
                if root := ".".join(parts[i + 1 :]):
                    return Domain.objects.filter(name__iexact=root).first()
                break

        return None

    def resolve_ptr(self, qname, qname_str):
        """Return PTR records for the sender subdomain of the queried SMTP IP.

        Only one PTR per IP is possible; return an empty list when the IP is
        not one of ours.
        """
        # <reversed-ip>.in-addr.arpa → "1.0.0.127" → "127.0.0.1"
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
