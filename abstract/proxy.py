"""Resolve the peers allowed to forward a client address."""

import ipaddress
from pathlib import Path

from django.conf import settings

ROUTE_TABLE = Path("/proc/net/route")


def get_trusted_proxy_hosts() -> list[str]:
    """Return the configured proxies plus the gateway this pod routes through."""
    hosts = [*settings.TRUSTED_PROXY_HOSTS]
    if gateway := get_default_gateway():
        hosts.append(gateway)
    return hosts


def get_default_gateway() -> str | None:
    """Return the IPv4 default gateway of this network namespace, if it has one."""
    try:
        routes = ROUTE_TABLE.read_text().splitlines()[1:]
    except OSError:
        return None
    defaults = [
        (int(fields[6]), fields[2])
        for fields in (line.split() for line in routes)
        if len(fields) >= 8 and fields[1] == "00000000" and fields[7] == "00000000"
    ]
    if not defaults:
        return None
    _, gateway = min(defaults)
    return str(ipaddress.IPv4Address(bytes.fromhex(gateway)[::-1]))
