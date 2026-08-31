"""ARC sealing of accepted inbound messages (RFC 8617)."""

import datetime
import logging
import time
from enum import StrEnum

import authres
import dkim
import dns.exception
import dns.resolver
import validators
from cryptography.fernet import InvalidToken
from django.conf import settings

from abstract.mailauth import DmarcEvaluation
from domains.models import Domain
from kms import keys

logger = logging.getLogger(__name__)

# RFC 8617 §3.9 caps the ARC instance tag at 50.
ARC_INSTANCE_LIMIT = 50

# Total time a DNS lookup may take.
DNS_LOOKUP_LIFETIME = datetime.timedelta(seconds=2)

# Total time chain verification may spend on DNS lookups.
ARC_CHAIN_VERIFICATION_TIMEOUT = datetime.timedelta(seconds=10)


class ChainResult(StrEnum):
    """Validation status of the incoming ARC chain."""

    NONE = "none"
    PASS = "pass"
    FAIL = "fail"
    TERMINATED = "terminated"


def clean_domain(value: str) -> str:
    """Return the value when it is a valid domain name, else an empty string."""
    return value if validators.domain(value) is True else ""


def create_authentication_results(
    evaluation: DmarcEvaluation, authserv_id: str, arc_result: ChainResult
) -> bytes:
    """Return the Authentication-Results header line for an evaluation.

    Result properties whose domain is not a plain domain name are omitted,
    so an attacker-controlled header value cannot inject clauses. The DMARC
    result is `temperror` when the policy lookup failed transiently, `none`
    when the sender domain publishes no DMARC policy, and `pass` only when
    an aligned SPF or DKIM mechanism passed (RFC 7489 §6.6.2). A terminated
    ARC chain is reported as `fail`, since RFC 8601 defines no `terminated`
    result.
    """
    if evaluation.dmarc_policy_temperror:
        dmarc_result = "temperror"
    elif evaluation.dmarc_policy_is_published:
        dmarc_result = "pass" if evaluation.dmarc_authenticated else "fail"
    else:
        dmarc_result = "none"
    arc_result = (
        ChainResult.FAIL if arc_result is ChainResult.TERMINATED else arc_result
    )
    header_from = clean_domain(evaluation.header_from)
    spf_domain = clean_domain(evaluation.spf_domain)
    dkim_domain = clean_domain(evaluation.dkim_domain)
    results = [
        f"arc={arc_result}",
        f"spf={evaluation.spf_result}"
        + (f" smtp.mailfrom={spf_domain}" if spf_domain else ""),
        f"dkim={evaluation.dkim_result}"
        + (f" header.d={dkim_domain}" if dkim_domain else ""),
        f"dmarc={dmarc_result} (dis={evaluation.disposition})"
        + (f" header.from={header_from}" if header_from else ""),
    ]
    return (f"Authentication-Results: {authserv_id}; " + "; ".join(results)).encode(
        "utf-8"
    )


def is_trusted_authentication_results(header_block: bytes, authserv_id: str) -> bool:
    """Return whether a multi-line header block may survive sealing.

    An Authentication-Results header is trusted when it parses and does
    not claim relay's authserv-id. All other header blocks are trusted.
    """
    name, _, value = header_block.partition(b":")
    if name.lower().rstrip(b" \t") != b"authentication-results":
        return True
    try:
        header = authres.AuthenticationResultsHeader.parse(
            "Authentication-Results: " + value.decode("utf-8").strip()
        )
    except authres.AuthResError, UnicodeDecodeError:
        return False
    return header.authserv_id != authserv_id


def remove_untrusted_authentication_results(
    raw_bytes: bytes, authserv_id: str
) -> bytes:
    """Return the message without Authentication-Results headers relay
    cannot vouch for.

    A header is dropped when it claims relay's authserv-id or when it
    cannot be parsed, so a spoofed or broken verdict cannot enter the
    seal. Header parsing ends like Python's email parser does, at a
    blank line or at a colon-less line that is not a continuation, so
    the body of a message without a header/body separator survives.
    A unix-from line (mbox envelope, starting with "From ") does not
    end the header section and is kept verbatim, since Python's email
    parser and dkimpy continue parsing headers after it.
    """
    kept: list[bytes] = []
    block: list[bytes] = []

    def flush_block():
        if is_trusted_authentication_results(b"".join(block), authserv_id):
            kept.extend(block)
        block.clear()

    in_headers = True
    for line in raw_bytes.splitlines(keepends=True):
        if not in_headers:
            kept.append(line)
        elif line.startswith(b"From "):
            flush_block()
            kept.append(line)
        elif not line.strip(b"\r\n") or (line[:1] not in b" \t" and b":" not in line):
            flush_block()
            kept.append(line)
            in_headers = False
        else:
            if block and line[:1] not in b" \t":
                flush_block()
            block.append(line)
    flush_block()
    return b"".join(kept)


def fetch_dkim_key_record(name: bytes, timeout: int = 5) -> bytes | None:
    """Return the first TXT record at a DKIM selector name, or None.

    The first TXT record is returned with its strings joined and without
    a v=DKIM1 filter, matching dkimpy's get_txt: RFC 6376 §3.6.1 makes
    the tag optional, and dkimpy's tag validation rejects non-key
    records itself. The timeout parameter is unused; it only exists to
    satisfy dkimpy's dnsfunc protocol. DNS lookups are bounded by
    DNS_LOOKUP_LIFETIME.
    """
    try:
        answer = dns.resolver.resolve(
            name.decode("utf-8"),
            "TXT",
            lifetime=DNS_LOOKUP_LIFETIME.total_seconds(),
        )
        return b"".join(answer[0].strings)
    except dns.exception.DNSException:
        return None


def verify_arc_chain(
    raw_bytes: bytes, dns_budget: datetime.timedelta = ARC_CHAIN_VERIFICATION_TIMEOUT
) -> ChainResult:
    """Return the ARC chain validation status of a message.

    DNS lookups are capped by the total dns_budget; once it is
    exhausted, further lookups return no key and the chain fails.
    """
    deadline = time.monotonic() + dns_budget.total_seconds()
    budget_exhausted = False

    def fetch_dkim_key_record_within_budget(
        name: bytes, timeout: int = 5
    ) -> bytes | None:
        nonlocal budget_exhausted
        if time.monotonic() >= deadline:
            if not budget_exhausted:
                budget_exhausted = True
                logger.warning("ARC chain verification DNS budget exhausted")
            return None
        return fetch_dkim_key_record(name, timeout)

    try:
        arc = dkim.ARC(raw_bytes)
        max_instance, _ = arc.sorted_arc_headers()
        if max_instance > ARC_INSTANCE_LIMIT:
            logger.warning(
                "ARC chain instance %d exceeds the limit of %d",
                max_instance,
                ARC_INSTANCE_LIMIT,
            )
            return ChainResult.FAIL
        chain_result = dkim.arc_verify(
            raw_bytes, dnsfunc=fetch_dkim_key_record_within_budget
        )[0]
    except dkim.DKIMException, IndexError, UnicodeDecodeError:
        logger.warning("ARC chain verification failed", exc_info=True)
        return ChainResult.FAIL
    return {
        dkim.CV_Pass: ChainResult.PASS,
        dkim.CV_None: ChainResult.NONE,
        None: ChainResult.TERMINATED,
    }.get(chain_result, ChainResult.FAIL)


def seal_message(
    raw_bytes: bytes, evaluation: DmarcEvaluation, domain: Domain
) -> bytes:
    """Seal an accepted message with relay's ARC set.

    Fall back to the message with relay's Authentication-Results header when
    the seal cannot be created. A chain whose most recent seal already
    reported failure is not extended (RFC 8617 §5.1).
    """
    authserv_id = domain.sender_domain
    raw_bytes = remove_untrusted_authentication_results(raw_bytes, authserv_id)
    chain_result = verify_arc_chain(raw_bytes)
    linesep = dkim.util.get_linesep(raw_bytes)
    raw_bytes = (
        create_authentication_results(evaluation, authserv_id, chain_result)
        + linesep
        + raw_bytes
    )
    if chain_result is ChainResult.TERMINATED:
        return raw_bytes
    key = domain.dkim_key_rsa2048
    if key is None:
        logger.warning("Missing RSA-2048 key for %s, skipping ARC seal", domain.name)
        return raw_bytes
    selector = f"{settings.RELAY_DNS_DKIM_IDENTIFIER}-rsa2048"
    try:
        privkey, _ = keys.dkim_key_material(key.encrypted_private_key, key.algorithm)
        arc_set = dkim.arc_sign(
            raw_bytes,
            selector.encode("ascii"),
            domain.name.encode("ascii"),
            privkey,
            authserv_id.encode("ascii"),
            linesep=linesep,
        )
    except dkim.ParameterError as exc:
        logger.warning("Skipping ARC seal for %s: %s", domain.name, exc)
        return raw_bytes
    except (
        dkim.DKIMException,
        UnicodeDecodeError,
        InvalidToken,
        ValueError,
    ):
        logger.exception("ARC sealing failed for %s (%s)", domain.name, selector)
        return raw_bytes
    return b"".join(arc_set) + raw_bytes
