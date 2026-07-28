"""Evaluate DMARC compliance for incoming messages."""

import ipaddress
import logging
import re
from email import message_from_bytes

import dkim
import dns.resolver

logger = logging.getLogger(__name__)

RECEIVED_IP_PATTERN = re.compile(r"\[(\d+\.\d+\.\d+\.\d+)\]|\[([0-9a-fA-F:]+)\]")
EMAIL_DOMAIN_PATTERN = re.compile(r"@([\w.-]+)")


def evaluate_dmarc(incoming_message):
    """Return DMARC evaluation results for an incoming message."""
    raw_bytes = incoming_message.raw_body.read()
    msg = message_from_bytes(raw_bytes)

    header_from_domain = extract_domain(msg.get("From", ""))
    envelope_from_domain = extract_domain(incoming_message.mail_from)
    source_ip = extract_source_ip(msg)

    dmarc_policy = lookup_dmarc_policy(header_from_domain)

    dkim_result, dkim_domain = verify_dkim(raw_bytes)
    spf_result, spf_domain = check_spf(source_ip, envelope_from_domain)

    dkim_aligned = check_alignment(
        dkim_domain, header_from_domain, dmarc_policy.get("adkim", "r")
    )
    spf_aligned = check_alignment(
        spf_domain, header_from_domain, dmarc_policy.get("aspf", "r")
    )

    disposition = determine_disposition(dmarc_policy, dkim_aligned, spf_aligned)

    return {
        "source_ip_address": source_ip,
        "header_from": header_from_domain,
        "envelope_from": envelope_from_domain,
        "dkim_domain": dkim_domain,
        "dkim_result": dkim_result,
        "dkim_alignment": "pass" if dkim_aligned else "fail",
        "spf_domain": spf_domain,
        "spf_result": spf_result,
        "spf_alignment": "pass" if spf_aligned else "fail",
        "disposition": disposition,
    }


def extract_domain(email_or_header):
    """Return the domain part of an email address or From header."""
    if match := EMAIL_DOMAIN_PATTERN.search(email_or_header):
        return match.group(1).lower()
    return email_or_header.lower().strip()


def extract_source_ip(msg):
    """Return the sending IP address from the first Received header."""
    for header in msg.get_all("Received", []):
        if match := RECEIVED_IP_PATTERN.search(header):
            ip_str = match.group(1) or match.group(2)
            try:
                ipaddress.ip_address(ip_str)
                return ip_str
            except ValueError:
                continue
    return None


def lookup_dmarc_policy(domain):
    """Return the DMARC TXT record parsed as a policy dict for a domain."""
    try:
        records = dns.resolver.resolve(f"_dmarc.{domain}", "TXT")
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return {}

    for record in records:
        text = "".join(
            s.decode() if isinstance(s, bytes) else s for s in record.strings
        )
        if not text.startswith("v=DMARC1"):
            continue
        policy = {}
        for part in text.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            key, value = (s.strip() for s in part.split("=", 1))
            if key in {"p", "sp", "adkim", "aspf", "rua", "ruf"}:
                policy[key] = value
            elif key == "pct":
                policy[key] = int(value)
        return policy
    return {}


def verify_dkim(raw_bytes):
    """Check DKIM signatures in a raw email and return the result with the signing domain."""
    try:
        verified = dkim.verify(raw_bytes)
    except dkim.DKIMException:
        return "permerror", ""

    if not verified:
        return "fail", ""

    msg = message_from_bytes(raw_bytes)
    for key, value in msg.items():
        if key.lower() != "dkim-signature":
            continue
        params = dict(
            s.strip().split("=", 1) for s in value.split(";") if "=" in s.strip()
        )
        domain = params.get("d", "")
        return "pass", domain
    return "pass", ""


def check_spf(source_ip, domain):
    """Validate a source IP against a domain's SPF record."""
    if not source_ip or not domain:
        return "none", domain

    try:
        records = dns.resolver.resolve(domain, "TXT")
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return "none", domain

    for record in records:
        text = "".join(
            s.decode() if isinstance(s, bytes) else s for s in record.strings
        )
        if not text.startswith("v=spf1"):
            continue
        if "a" in text or "mx" in text or f"ip4:{source_ip}" in text:
            return "pass", domain
        if "~all" in text or "-all" in text:
            return "fail", domain
        if "+all" in text or "?all" in text:
            return "neutral", domain
        return "neutral", domain
    return "none", domain


def check_alignment(auth_domain, header_from_domain, policy):
    """Determine if an authenticated domain aligns with the header-from domain."""
    if not auth_domain or not header_from_domain:
        return False

    mode = policy if isinstance(policy, str) else "r"
    match mode:
        case "s":  # strict
            return auth_domain.lower() == header_from_domain.lower()
        case _:  # relaxed (default)
            auth = auth_domain.lower()
            header = header_from_domain.lower()
            return (
                auth == header
                or auth.endswith(f".{header}")
                or header.endswith(f".{auth}")
            )


def determine_disposition(policy, dkim_aligned, spf_aligned):
    """Return the DMARC disposition based on policy and alignment."""
    if dkim_aligned or spf_aligned:
        return "none"
    return policy.get("p", "none")
