"""DNS verification services. Validates NS delegation and DMARC on root domain."""

import re

import dns.resolver
from django.conf import settings
from django.utils import timezone

from .models import Domain

MTA_STS_EXTENSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}")
MTA_STS_EXTENSION_VALUE = re.compile(r"[\x21-\x3A\x3C\x3E-\x7E]+")


def parse_mta_sts_txt_record(value):
    """Return valid MTA-STS tags, or `None` for a malformed record."""
    fields = value.split(";")
    if fields[0] != "v=STSv1":
        return None
    if fields[-1].strip(" \t") == "":
        fields.pop()

    tags = {}
    for field in fields[1:]:
        field = field.strip(" \t")
        if "=" not in field:
            return None
        name, tag_value = field.split("=", 1)
        if name in tags:
            return None
        if name == "id":
            if re.fullmatch(r"[A-Za-z0-9]{1,32}", tag_value) is None:
                return None
        elif (
            MTA_STS_EXTENSION_NAME.fullmatch(name) is None
            or MTA_STS_EXTENSION_VALUE.fullmatch(tag_value) is None
        ):
            return None
        tags[name] = tag_value
    return tags if "id" in tags else None


def verify_nameserver_delegation(domain):
    try:
        ns_records = dns.resolver.resolve(domain.sender_domain, "NS")
        our_ns = {ns.rstrip(".").lower() for ns in settings.RELAY_DNS_NS_NAMESERVERS}
        their_ns = {str(r.target).rstrip(".").lower() for r in ns_records}
        return our_ns == their_ns
    except dns.exception.DNSException:
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
    except dns.exception.DNSException:
        return False


def check_spf(domain):
    try:
        txt_records = dns.resolver.resolve(domain.name, "TXT")
        return any(
            domain.sender_domain
            in "".join(s.decode() if isinstance(s, bytes) else s for s in r.strings)
            for r in txt_records
        )
    except dns.exception.DNSException:
        return False


def check_dkim_cname(domain):
    try:
        return all(
            bool(dns.resolver.resolve(cname_name, "CNAME"))
            for cname_name, _ in domain.dkim_cnames
        )
    except dns.exception.DNSException:
        return False


def check_mta_sts(domain):
    try:
        txt_records = dns.resolver.resolve(f"_mta-sts.{domain.name}", "TXT")
        candidate_records = []
        for txt_record in txt_records:
            value = "".join(
                string.decode("ascii")
                if isinstance(string, bytes)
                else string.encode("ascii").decode("ascii")
                for string in txt_record.strings
            )
            if value.startswith("v=STSv1;"):
                candidate_records.append(value)
        if (
            len(candidate_records) != 1
            or parse_mta_sts_txt_record(candidate_records[0]) is None
        ):
            return False

        cname_records = dns.resolver.resolve(f"mta-sts.{domain.name}", "CNAME")
        expected_target = f"mta-sts.{domain.sender_domain}."
        cname_is_valid = any(
            str(record.target).lower() == expected_target.lower()
            for record in cname_records
        )
        return cname_is_valid
    except dns.exception.DNSException, UnicodeError:
        return False


def check_tls_rpt(domain):
    try:
        txt_records = dns.resolver.resolve(f"_smtp._tls.{domain.name}", "TXT")
        expected_reporting_uri = f"mailto:{domain.tls_reporting_address}".lower()
        for txt_record in txt_records:
            value = "".join(
                string.decode() if isinstance(string, bytes) else string
                for string in txt_record.strings
            )
            fields = [field.strip() for field in value.split(";")]
            match fields:
                case [version, *tag_fields] if version.lower() == "v=tlsrptv1":
                    tags = {}
                    for field in tag_fields:
                        if "=" in field:
                            tag_name, tag_value = field.split("=", 1)
                            tags[tag_name.strip().lower()] = tag_value.strip()
                    reporting_uris = {
                        uri.strip().lower().split("!", 1)[0]
                        for uri in tags.get("rua", "").split(",")
                    }
                    if expected_reporting_uri in reporting_uris:
                        return True
        return False
    except dns.exception.DNSException:
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
        except dns.exception.DNSException as error:
            setattr(domain, f"{field}_status", Domain.Status.ERROR)
            setattr(domain, f"{field}_error", str(error))

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
