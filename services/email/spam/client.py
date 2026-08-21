"""rspamd spam-detection client."""

import logging
from dataclasses import dataclass
from enum import StrEnum

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class SpamAction(StrEnum):
    NO_ACTION = "no action"
    GREYLIST = "greylist"
    ADD_HEADER = "add header"
    REWRITE_SUBJECT = "rewrite subject"
    SOFT_REJECT = "soft reject"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class SpamResult:
    """Outcome of a rspamd scan."""

    score: float = 0.0
    action: SpamAction = SpamAction.NO_ACTION

    @classmethod
    def from_response(cls, data: dict) -> SpamResult:
        """Create a SpamResult from a rspamd /checkv2 JSON response."""
        score = float(data.get("score") or 0.0)
        try:
            action = SpamAction(data.get("action", "no action"))
        except ValueError:
            action = SpamAction.NO_ACTION
        return cls(score=score, action=action)


async def check_message(raw_bytes: bytes, client_ip: str) -> SpamResult:
    """Return the rspamd score and action for a raw message.

    Fails open: on any rspamd error a neutral result is returned so mail is
    never lost during an outage. This is a deliberate availability trade-off.
    """
    headers = {"Ip": client_ip} if client_ip else {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{settings.RELAY_RSPAMD_URL.rstrip('/')}/checkv2",
                content=raw_bytes,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):  # fmt: skip
        logger.warning("rspamd check failed", exc_info=True)
        return SpamResult()
    return SpamResult.from_response(data)
