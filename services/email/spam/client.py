"""rspamd spam-detection client."""

from dataclasses import dataclass
from enum import StrEnum

import httpx
from django.conf import settings


class SpamAction(StrEnum):
    NO_ACTION = "no action"
    GREYLIST = "greylist"
    ADD_HEADER = "add header"
    REWRITE_SUBJECT = "rewrite subject"
    SOFT_REJECT = "soft reject"
    REJECT = "reject"


class ScannerUnavailableError(Exception):
    """
    rspamd reported `soft reject`: no verdict right now.

    The message is unscanned; the caller must retry it later.
    """


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
    """
    Return the rspamd score and action for a raw message.

    Raise `ScannerUnavailableError` when rspamd reports `soft reject`.
    """
    headers = {"Ip": client_ip} if client_ip else {}
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.RELAY_RSPAMD_URL.rstrip('/')}/checkv2",
            content=raw_bytes,
            headers=headers,
        )
        response.raise_for_status()
    result = SpamResult.from_response(response.json())
    if result.action == SpamAction.SOFT_REJECT:
        raise ScannerUnavailableError
    return result
