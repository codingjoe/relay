import logging
from dataclasses import dataclass, field
from fnmatch import fnmatch

import httpx
from django.core.cache import cache

logger = logging.getLogger(__name__)


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
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        mode, mx_patterns, max_age, policy_id = "", [], 3600, ""
        for line in response.text.splitlines():
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
        """
        Return the MTA-STS policy for *domain*.

        Fetches and caches the policy on a cache miss.
        """
        if cached := cache.get(f"mta-sts:{domain}"):
            return cached
        try:
            policy = cls.fetch(domain)
        except httpx.HTTPError, OSError:
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
                logger.warning("MTA-STS testing: MX %r not in policy", mx_hostname)
                return True, "MTA-STS testing mode, MX not in policy"
            case "enforce":
                return False, f"MTA-STS enforce: MX {mx_hostname} not allowed"
            case _:
                return True, f"MTA-STS mode {self.mode or 'none'} permits all MX"
