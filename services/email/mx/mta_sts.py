import logging
from dataclasses import dataclass, field
from fnmatch import fnmatch

import httpx
from django.core.cache import cache

from abstract.network import (
    UnsafeNetworkOperation,
    global_http_client,
    read_bounded_response_text,
    validate_global_url,
)

logger = logging.getLogger(__name__)

MTA_STS_POLICY_MAX_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class MtaStsPolicy:
    mode: str = ""
    mx_patterns: list[str] = field(default_factory=list)
    max_age: int = 3600
    policy_id: str = ""
    loaded: bool = False

    @classmethod
    def fetch(cls, domain):
        """Retrieve and parse the MTA-STS policy for *domain* over HTTPS."""
        url = f"https://mta-sts.{domain}/.well-known/mta-sts.txt"
        validate_global_url(url)
        with (
            global_http_client() as client,
            client.stream("GET", url, timeout=10) as response,
        ):
            response.raise_for_status()
            response_text = read_bounded_response_text(
                response, MTA_STS_POLICY_MAX_BYTES
            )
        mode, mx_patterns, max_age, policy_id = "", [], 3600, ""
        for line in response_text.splitlines():
            line = line.strip()
            if line and ":" in line:
                key, _, value = line.partition(":")
                match key.strip().lower():
                    case "mode":
                        mode = value.strip()
                    case "mx":
                        mx_patterns.append(value.strip())
                    case "max_age":
                        max_age = int(value.strip())
                    case "sts_id":
                        policy_id = value.strip()
        return cls(
            mode=mode,
            mx_patterns=mx_patterns,
            max_age=max_age,
            policy_id=policy_id,
            loaded=True,
        )

    @classmethod
    def get(cls, domain):
        """Return the MTA-STS policy for *domain*. The method fetches and
        caches the policy on a cache miss."""
        if cached := cache.get(f"mta-sts:{domain}"):
            return cached
        try:
            policy = cls.fetch(domain)
        except httpx.HTTPError, UnsafeNetworkOperation:
            policy = cls()
        cache.set(f"mta-sts:{domain}", policy, timeout=policy.max_age)
        return policy

    def allows(self, mx_hostname):
        """Return whether the policy allows the MX hostname."""
        if not self.loaded:
            return True, "No MTA-STS policy or fetch failed"

        if any(fnmatch(mx_hostname.lower(), p.lower()) for p in self.mx_patterns):
            return True, "MX matches MTA-STS pattern"

        match self.mode:
            case "testing":
                logger.warning("MTA-STS testing: MX %s not in policy", mx_hostname)
                return True, "MTA-STS testing mode, MX not in policy"
            case "enforce":
                return False, f"MTA-STS enforce: MX {mx_hostname} not allowed"
            case _:
                return True, f"MTA-STS mode {self.mode or 'none'} permits all MX"
