"""MTA-STS policy checks for outbound delivery."""

import logging
from fnmatch import fnmatch

from .models import MtaStsPolicy

logger = logging.getLogger(__name__)


def check_mta_sts(recipient_domain, mx_hostname):
    """Check if the MX hostname is allowed by the recipient's MTA-STS policy.

    Returns an (allowed, reason) tuple.
    """
    policy = MtaStsPolicy.get_or_fetch(recipient_domain)

    if policy.status != MtaStsPolicy.Status.LOADED:
        return True, "No MTA-STS policy or fetch failed"

    if any(fnmatch(mx_hostname.lower(), p.lower()) for p in policy.mx_patterns):
        return True, f"MX matches MTA-STS pattern for {recipient_domain}"

    match policy.mode:
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
            return True, f"MTA-STS mode {policy.mode or 'none'} permits all MX"
