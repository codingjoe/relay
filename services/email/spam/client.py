"""rspamd spam-detection client."""

import logging
from dataclasses import dataclass

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

KNOWN_ACTIONS = frozenset(
    {"no action", "greylist", "add header", "rewrite subject", "soft reject", "reject"}
)


@dataclass(frozen=True)
class SpamResult:
    """Outcome of a rspamd scan."""

    score: float = 0.0
    action: str = "no action"

    def add_headers(self, raw_bytes: bytes) -> bytes:
        """Return the raw message with X-Spam headers prepended."""
        headers = (
            f"X-Spam-Score: {self.score}\r\nX-Spam-Action: {self.action}\r\n"
        ).encode()
        return headers + raw_bytes


async def check_message(raw_bytes: bytes) -> SpamResult:
    """Return the rspamd score and action for a raw message.

    Fails open: on any rspamd error a neutral result is returned so mail is
    never lost during an outage. This is a deliberate availability trade-off.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.RELAY_RSPAMD_URL.rstrip('/')}/checkv2",
                content=raw_bytes,
            )
            response.raise_for_status()
            data = response.json()
            score = float(data.get("score") or 0.0)
            action = data.get("action", "no action")
            if action not in KNOWN_ACTIONS:
                action = "no action"
            return SpamResult(score=score, action=action)
    except (httpx.HTTPError, ValueError, TypeError) as error:
        logger.warning("rspamd check failed: %s", error)
        return SpamResult()
