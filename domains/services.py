"""DNS verification services. Validates NS delegation and DMARC on root domain."""

import dns.resolver
from django.conf import settings
from django.utils import timezone

from .models import Domain


def verify_nameserver_delegation(domain):
    try:
        ns_records = dns.resolver.resolve(domain.sender_domain, "NS")
        our_ns = {ns.rstrip(".").lower() for ns in settings.RELAY_DNS_NS_NAMESERVERS}
        their_ns = {str(r.target).rstrip(".").lower() for r in ns_records}
        return our_ns == their_ns
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return False


def check_dmarc(domain):
    try:
        txt_records = dns.resolver.resolve(domain.dmarc_record_name, "TXT")
        return any(
            "".join(
                s.decode() if isinstance(s, bytes) else s for s in r.strings
            ).startswith("v=DMARC1")
            for r in txt_records
        )
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return False


def check_spf(domain):
    try:
        txt_records = dns.resolver.resolve(domain.name, "TXT")
        return any(
            domain.sender_domain
            in "".join(s.decode() if isinstance(s, bytes) else s for s in r.strings)
            for r in txt_records
        )
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return False


def check_dkim_cname(domain):
    try:
        return all(
            bool(dns.resolver.resolve(cname_name, "CNAME"))
            for cname_name, _ in domain.dkim_cnames
        )
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return False


def check_mta_sts(domain):
    try:
        txt_records = dns.resolver.resolve(f"_mta-sts.{domain.name}", "TXT")
        return any(
            "".join(
                s.decode() if isinstance(s, bytes) else s for s in r.strings
            ).startswith("v=STSv1")
            for r in txt_records
        )
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return False


def check_tls_rpt(domain):
    try:
        txt_records = dns.resolver.resolve(f"_smtp._tls.{domain.name}", "TXT")
        return any(
            "".join(
                s.decode() if isinstance(s, bytes) else s for s in r.strings
            ).startswith("v=TLSRPTv1")
            for r in txt_records
        )
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return False


def verify_domain_dns(domain):
    """Run DNS checks for a domain and update its status fields."""
    checks = {
        "nameserver": verify_nameserver_delegation,
        "spf": check_spf,
        "dkim": check_dkim_cname,
        "dmarc": check_dmarc,
        "mta_sts": check_mta_sts,
        "tls_rpt": check_tls_rpt,
    }

    for field, check_fn in checks.items():
        try:
            ok = check_fn(domain)
            setattr(
                domain,
                f"{field}_status",
                Domain.Status.OK if ok else Domain.Status.ERROR,
            )
            setattr(
                domain,
                f"{field}_error",
                "" if ok else f"{field} record not found or incorrect",
            )
        except (
            dns.resolver.NXDOMAIN,
            dns.resolver.NoAnswer,
            dns.exception.Timeout,
        ) as e:
            setattr(domain, f"{field}_status", Domain.Status.ERROR)
            setattr(domain, f"{field}_error", str(e))

    domain.dns_checked_at = timezone.now()

    if (
        all(getattr(domain, f"{f}_status") == Domain.Status.OK for f in checks)
        and domain.verified_at is None
    ):
        domain.verified_at = timezone.now()

    domain.save(
        update_fields=[
            "nameserver_status",
            "nameserver_error",
            "spf_status",
            "spf_error",
            "dkim_status",
            "dkim_error",
            "dmarc_status",
            "dmarc_error",
            "mta_sts_status",
            "mta_sts_error",
            "tls_rpt_status",
            "tls_rpt_error",
            "dns_checked_at",
            "verified_at",
        ]
    )
