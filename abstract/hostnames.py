import ipaddress
import logging

import dns.exception
import dns.resolver
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

SENDER_HOSTNAME_CACHE_SECONDS = 3600


def resolve_hostname(address: str) -> str:
    """Return the reverse-DNS hostname of a public IP address, if one exists."""
    hostname = ""
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.is_global:
        try:
            answer = dns.resolver.resolve(parsed.reverse_pointer, "PTR", lifetime=2.0)
        except dns.resolver.NXDOMAIN, dns.resolver.NoAnswer:
            answer = None
        except dns.exception.Timeout, dns.resolver.NoNameservers:
            logger.warning("Reverse DNS lookup failed for %r", address, exc_info=True)
            answer = None
        except dns.exception.DNSException:
            logger.warning(
                "Reverse DNS lookup failed for malformed address %r",
                address,
                exc_info=True,
            )
            answer = None
        if answer is not None:
            hostname = str(answer[0]).rstrip(".")
    return hostname


def is_relay_address(address):
    """Return whether the address belongs to relay's sending pool."""
    return address in settings.SMTP_SOURCE_IPS or address in settings.DNS_SMTP_IPS


def lookup_sender_hostname(address):
    """Return the cached reverse-DNS hostname of a relay sending address."""
    cache_key = f"relay:sender-hostname:{address}"
    hostname = cache.get(cache_key)
    if hostname is None:
        hostname = resolve_hostname(address)
        cache.set(cache_key, hostname, timeout=SENDER_HOSTNAME_CACHE_SECONDS)
    return hostname


def add_sender_hostname(report, address):
    """Attach the reverse-DNS hostname to a report from a relay address."""
    if is_relay_address(address):
        report.sender_hostname = lookup_sender_hostname(address)
