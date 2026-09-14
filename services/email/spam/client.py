"""rspamd spam-detection client."""

from dataclasses import dataclass, field
from enum import StrEnum

import httpx
from django.conf import settings

# rspamd reuses `soft reject` for greylisting and rate limiting, so the failure
# symbol is the only signal that a scan did not complete.
SCANNER_FAILURE_SYMBOL = "CLAM_VIRUS_FAIL"
VIRUS_SYMBOL = "CLAM_VIRUS"
VIRUS_ENCRYPTED_SYMBOL = "CLAM_VIRUS_ENCRYPTED"
VIRUS_MACRO_SYMBOL = "CLAM_VIRUS_MACRO"
VIRUS_LIMITS_SYMBOL = "CLAM_VIRUS_LIMITS"
# rspamd derives every antivirus symbol from the main one, and adds none of
# them when a scan comes back clean.
ANTIVIRUS_SYMBOL_PREFIX = VIRUS_SYMBOL


class SpamAction(StrEnum):
    NO_ACTION = "no action"
    GREYLIST = "greylist"
    ADD_HEADER = "add header"
    REWRITE_SUBJECT = "rewrite subject"
    SOFT_REJECT = "soft reject"
    REJECT = "reject"


class VirusAction(StrEnum):
    CLEAN = "clean"
    INFECTED = "infected"
    ENCRYPTED = "encrypted"
    MACRO = "macro"
    LIMITS = "limits"


# A detection outranks an uninspectable part, which outranks a scanner limit.
VIRUS_SYMBOL_VERDICTS = (
    (VIRUS_SYMBOL, VirusAction.INFECTED),
    (VIRUS_ENCRYPTED_SYMBOL, VirusAction.ENCRYPTED),
    (VIRUS_MACRO_SYMBOL, VirusAction.MACRO),
    (VIRUS_LIMITS_SYMBOL, VirusAction.LIMITS),
)


class ScannerUnavailableError(Exception):
    """ClamAV did not complete a scan, so the message is still unscanned."""


@dataclass(frozen=True, slots=True)
class SpamResult:
    """Outcome of a rspamd scan."""

    score: float = 0.0
    action: SpamAction = SpamAction.NO_ACTION
    virus_action: VirusAction = VirusAction.CLEAN
    virus_name: str = ""
    virus_symbols: dict[str, dict] = field(default_factory=dict)
    scan_ms: float | None = None
    antivirus_ms: float | None = None
    profile_ms: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_response(cls, data: dict) -> SpamResult:
        """Create a SpamResult from a rspamd /checkv2 JSON response."""
        symbols = {
            name: symbol
            for name, symbol in data["symbols"].items()
            # The failure symbol raises in check_message, so it gets no verdict.
            if name.startswith(ANTIVIRUS_SYMBOL_PREFIX)
            and name != SCANNER_FAILURE_SYMBOL
        }
        virus_action = VirusAction.CLEAN
        for symbol, verdict in VIRUS_SYMBOL_VERDICTS:
            if symbol in symbols:
                virus_action = verdict
                break
        virus_options = symbols.get(VIRUS_SYMBOL, {}).get("options") or []
        score = float(data.get("score") or 0.0)
        try:
            action = SpamAction(data.get("action", "no action"))
        except ValueError:
            action = SpamAction.NO_ACTION
        # rspamd profiles a sample of tasks, so the map is usually empty.
        profile_ms = {
            name: round(float(timing), 1)
            for name, timing in (data.get("profile") or {}).items()
        }
        antivirus_ms = (
            round(
                sum(
                    timing
                    for name, timing in profile_ms.items()
                    if name.startswith(ANTIVIRUS_SYMBOL_PREFIX)
                ),
                1,
            )
            or None
        )
        time_real_secs = data.get("time_real")
        scan_ms = (
            None if time_real_secs is None else round(float(time_real_secs) * 1000, 1)
        )
        return cls(
            score=score,
            action=action,
            virus_action=virus_action,
            virus_name=str(virus_options[0]) if virus_options else "",
            virus_symbols=symbols,
            scan_ms=scan_ms,
            antivirus_ms=antivirus_ms,
            profile_ms=profile_ms,
        )


async def check_message(raw_bytes: bytes, client_ip: str) -> SpamResult:
    """Return the rspamd score and action for a raw message."""
    headers = {
        "Password": settings.RELAY_RSPAMD_PASSWORD,
        # Symbol timings come back only for profiled tasks, see
        # https://docs.rspamd.com/developers/protocol/
        "Profile": "yes",
    }
    if client_ip:
        headers["Ip"] = client_ip
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            f"{settings.RELAY_RSPAMD_URL.rstrip('/')}/checkv2",
            content=raw_bytes,
            headers=headers,
        )
        response.raise_for_status()
    data = response.json()
    if SCANNER_FAILURE_SYMBOL in data["symbols"]:
        raise ScannerUnavailableError
    return SpamResult.from_response(data)
