import ipaddress
import logging
import re
from email import message_from_bytes

import dkim
import dns.resolver

from .types import AuthResult

logger = logging.getLogger(__name__)

RECEIVED_IP_PATTERN = re.compile(r"\[(\d+\.\d+\.\d+\.\d+)\]|\[([0-9a-fA-F:]+)\]")
EMAIL_DOMAIN_PATTERN = re.compile(r"@([\w.-]+)")


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


def verify_dkim(raw_bytes):
    """Check DKIM signatures in a raw email and return the result with the signing domain."""
    try:
        verified = dkim.verify(raw_bytes)
    except dkim.DKIMException:
        return AuthResult.PERMERROR, ""

    if verified:
        msg = message_from_bytes(raw_bytes)
        for key, value in msg.items():
            if key.lower() == "dkim-signature":
                params = dict(
                    s.strip().split("=", 1)
                    for s in value.split(";")
                    if "=" in s.strip()
                )
                return AuthResult.PASS, params.get("d", "")
        return AuthResult.PASS, ""

    return AuthResult.FAIL, ""


def check_spf(source_ip, domain):
    """Validate a source IP against a domain's SPF record."""
    if not source_ip or not domain:
        return AuthResult.NONE, domain

    try:
        records = dns.resolver.resolve(domain, "TXT")
    except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout:
        return AuthResult.NONE, domain

    for record in records:
        text = "".join(
            s.decode() if isinstance(s, bytes) else s for s in record.strings
        )
        if not text.startswith("v=spf1"):
            continue
        if "a" in text or "mx" in text or f"ip4:{source_ip}" in text:
            return AuthResult.PASS, domain
        if "~all" in text or "-all" in text:
            return AuthResult.FAIL, domain
        if "+all" in text or "?all" in text:
            return AuthResult.NEUTRAL, domain
        return AuthResult.NEUTRAL, domain
    return AuthResult.NONE, domain


def check_alignment(auth_domain, header_from_domain, policy):
    """Determine if an authenticated domain aligns with the header-from domain."""
    if not auth_domain or not header_from_domain:
        return False

    mode = policy if isinstance(policy, str) else "r"
    auth = auth_domain.lower()
    header = header_from_domain.lower()
    match mode:
        case "s":
            return auth == header
        case _:
            return (
                auth == header
                or auth.endswith(f".{header}")
                or header.endswith(f".{auth}")
            )
