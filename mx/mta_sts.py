"""MTA-STS policy checks for outbound delivery."""

import logging
from fnmatch import fnmatch

import httpx
from django.core.cache import cache

logger = logging.getLogger(__name__)

DEFAULT_MAX_AGE = 3600


def fetch_mta_sts_policy(domain):
    """Retrieve and parse the MTA-STS policy for *domain* over HTTPS."""
    url = f"https://mta-sts.{domain}/.well-known/mta-sts.txt"
    policy = {
        "mode": "",
        "mx_patterns": [],
        "max_age": DEFAULT_MAX_AGE,
        "policy_id": "",
        "status": "none",
    }
    response = httpx.get(url, timeout=10)
    response.raise_for_status()
    for line in response.text.splitlines():
        line = line.strip()
        if line and ":" in line:
            key, _, value = line.partition(":")
            match key.strip().lower():
                case "mode":
                    policy["mode"] = value.strip()
                case "mx":
                    policy["mx_patterns"].append(value.strip())
                case "max_age":
                    policy["max_age"] = int(value.strip())
                case "sts_id":
                    policy["policy_id"] = value.strip()
    policy["status"] = "loaded"
    return policy


def get_mta_sts_policy(domain):
    """Return the MTA-STS policy for *domain*, fetching and caching on miss."""
    if cached := cache.get(f"mta-sts:{domain}"):
        return cached
    try:
        policy = fetch_mta_sts_policy(domain)
    except httpx.HTTPError, OSError:
        policy = {
            "mode": "",
            "mx_patterns": [],
            "max_age": DEFAULT_MAX_AGE,
            "policy_id": "",
            "status": "none",
        }
    cache.set(f"mta-sts:{domain}", policy, timeout=policy["max_age"])
    return policy


def check_mta_sts(recipient_domain, mx_hostname):
    """Validate if the MX hostname is allowed by the recipient's MTA-STS policy."""
    policy = get_mta_sts_policy(recipient_domain)

    if policy["status"] != "loaded":
        return True, "No MTA-STS policy or fetch failed"

    if any(fnmatch(mx_hostname.lower(), p.lower()) for p in policy["mx_patterns"]):
        return True, f"MX matches MTA-STS pattern for {recipient_domain}"

    match policy["mode"]:
        case "testing":
            logger.warning(
                "MTA-STS testing: MX %s not in policy for %s",
                mx_hostname,
                recipient_domain,
            )
            return True, "MTA-STS testing mode, MX not in policy"
        case "enforce":
            return (
                False,
                f"MTA-STS enforce: MX {mx_hostname} not allowed for {recipient_domain}",
            )
        case _:
            return True, f"MTA-STS mode {policy['mode'] or 'none'} permits all MX"
