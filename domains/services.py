"""DNS verification services. Validates NS delegation and DMARC on root domain."""

import re
from functools import partial

import dns.resolver
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import Domain

MTA_STS_EXTENSION_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,31}")
MTA_STS_EXTENSION_VALUE = re.compile(r"[\x21-\x3A\x3C\x3E-\x7E]+")

CHECK_LABELS = {
    "nameserver": "NS",
    "spf": "SPF",
    "dkim_rsa2048": "RSA-2048 DKIM",
    "dkim_ed25519": "Ed25519 DKIM",
    "dmarc": "DMARC",
    "mx": "MX",
    "mta_sts": "MTA-STS",
    "tls_rpt": "TLS-RPT",
}

CHECK_ERRORS = {
    "dmarc": _("DMARC record or reporting addresses not found or incorrect."),
    "mta_sts": _("MTA-STS record or MX hosts not found or incorrect."),
}


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
    except dns.exception.DNSException:
        return False
    our_ns = {ns.rstrip(".").lower() for ns in settings.DNS_NS_NAMESERVERS}
    their_ns = {str(r.target).rstrip(".").lower() for r in ns_records}
    # A chased CNAME answers with the target's records, so the owner name of
    # the answer is what proves a zone cut, and the nameserver set alone does not.
    return (
        str(ns_records.rrset.name).rstrip(".").lower() == domain.sender_domain.lower()
        and our_ns == their_ns
    )


def check_dmarc(domain):
    try:
        txt_records = dns.resolver.resolve(domain.dmarc_record_name, "TXT")
    except dns.exception.DNSException:
        return False

    dmarc_records = []
    for record in txt_records:
        value = "".join(
            string.decode() if isinstance(string, bytes) else string
            for string in record.strings
        )
        if value.startswith("v=DMARC1"):
            dmarc_records.append(value)
    if len(dmarc_records) != 1:
        return False

    tags = {}
    for field in dmarc_records[0].split(";"):
        name, separator, value = field.partition("=")
        if separator:
            tags[name.strip().lower()] = value.strip()

    def parse_reporting_addresses(tag):
        return {
            uri.strip().split("!", 1)[0].lower()
            for uri in tags.get(tag, "").split(",")
            if uri.strip()
        }

    return (
        f"mailto:{domain.dmarc_reporting_address}".lower()
        in parse_reporting_addresses("rua")
        and f"mailto:{domain.dmarc_ruf_reporting_address}".lower()
        in parse_reporting_addresses("ruf")
    )


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


def check_dkim_cname(domain, field):
    name, target = domain.dkim_cnames[field]
    try:
        cname_records = dns.resolver.resolve(name, "CNAME")
    except dns.exception.DNSException:
        return False
    # relay serves the key at the documented target and nowhere else, so the
    # record's own name, a loop, leaves the signature unverifiable.
    return any(
        str(record.target).lower() == f"{target}.".lower() for record in cname_records
    )


def check_mx(domain):
    try:
        mx_records = dns.resolver.resolve(domain.name, "MX")
    except dns.exception.DNSException:
        return False
    expected_exchanges = {
        hostname.rstrip(".").lower() for hostname in settings.DNS_MX_HOSTNAMES
    }
    return any(
        str(record.exchange).rstrip(".").lower() in expected_exchanges
        for record in mx_records
    )


def matches_mta_sts_mx_pattern(hostname, pattern):
    """Return whether an MX hostname matches an MTA-STS mx pattern."""
    hostname = hostname.rstrip(".").lower()
    pattern = pattern.rstrip(".").lower()
    if pattern.startswith("*."):
        label, _, suffix = hostname.partition(".")
        matches = bool(label) and suffix == pattern.removeprefix("*.")
    else:
        matches = hostname == pattern
    return matches


def check_mta_sts(domain):
    try:
        mx_records = dns.resolver.resolve(domain.name, "MX")
        mx_hosts = {str(record.exchange).rstrip(".").lower() for record in mx_records}
        if not mx_hosts or not all(
            any(
                matches_mta_sts_mx_pattern(hostname, pattern)
                for pattern in domain.mta_sts_mx_hosts
            )
            for hostname in mx_hosts
        ):
            return False

        txt_records = dns.resolver.resolve(domain.mta_sts_record_name, "TXT")
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
        if len(candidate_records) != 1:
            return False
        tags = parse_mta_sts_txt_record(candidate_records[0])
        if tags is None or tags["id"] != domain.mta_sts_policy_id:
            return False

        cname_records = dns.resolver.resolve(domain.mta_sts_hostname, "CNAME")
        expected_target = f"{domain.mta_sts_cname_target}."
        return any(
            str(record.target).lower() == expected_target.lower()
            for record in cname_records
        )
    except dns.exception.DNSException, UnicodeError:
        return False


def check_tls_rpt(domain):
    try:
        txt_records = dns.resolver.resolve(domain.tls_rpt_record_name, "TXT")
    except dns.exception.DNSException:
        return False
    candidate_records = []
    for txt_record in txt_records:
        value = "".join(
            string.decode() if isinstance(string, bytes) else string
            for string in txt_record.strings
        )
        if value.startswith("v=TLSRPTv1;"):
            candidate_records.append(value)
    if len(candidate_records) != 1:
        return False
    tags = {}
    for field in candidate_records[0].split(";")[1:]:
        name, separator, tag_value = field.partition("=")
        if separator:
            tags[name.strip().lower()] = tag_value.strip()
    expected_reporting_uri = f"mailto:{domain.tls_reporting_address}".lower()
    reporting_uris = {
        uri.strip().lower().split("!", 1)[0]
        for uri in tags.get("rua", "").split(",")
        if uri.strip()
    }
    return expected_reporting_uri in reporting_uris


def verify_domain_dns(domain):
    """Run DNS checks for a domain and update its status fields."""
    checks = {
        "nameserver": verify_nameserver_delegation,
        "spf": check_spf,
        "dmarc": check_dmarc,
        "mx": check_mx,
        "mta_sts": check_mta_sts,
        "tls_rpt": check_tls_rpt,
    } | {field: partial(check_dkim_cname, field=field) for field in domain.dkim_cnames}

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
                ""
                if ok
                else CHECK_ERRORS.get(
                    field,
                    _("%(name)s record not found or incorrect.")
                    % {"name": CHECK_LABELS[field]},
                ),
            )
        except dns.exception.DNSException as error:
            setattr(domain, f"{field}_status", Domain.Status.ERROR)
            setattr(domain, f"{field}_error", str(error))

    domain.dns_checked_at = timezone.now()

    # Only the quick start group gates sending, so the rest stay optional.
    if domain.is_sending_verified and domain.verified_at is None:
        domain.verified_at = timezone.now()

    domain.save(
        update_fields=[
            *(
                attribute
                for field in checks
                for attribute in (f"{field}_status", f"{field}_error")
            ),
            "dns_checked_at",
            "verified_at",
        ]
    )
