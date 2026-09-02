"""DKIM signing and verification for outbound messages."""

import logging
from email import message_from_bytes

import dkim
from django.conf import settings
from django.db.models import Q

from abstract.mailauth import AuthResult

from .models import Domain
from .resolver import dkim_record

logger = logging.getLogger(__name__)

INCLUDE_HEADERS = ["From", "To", "Subject", "Date", "Message-ID", "Feedback-ID"]


def add_dkim_signature(raw_bytes, selector, domain_name, key, include_headers):
    """Prepend a DKIM signature to the message, or return it unchanged on failure."""
    try:
        return (
            key.sign_dkim(raw_bytes, selector, domain_name, include_headers) + raw_bytes
        )
    except dkim.DKIMException, ValueError:
        logger.exception("DKIM signing failed for %s (%s)", domain_name, selector)
        return raw_bytes


def sign_message(raw_bytes, domain):
    """
    Sign a message with DKIM for the sender domain.

    Also signs for the domain named RELAY_PLATFORM_DOMAIN when it exists.
    """
    signed = raw_bytes
    # Signatures are prepended, so the customer's signature ends up on
    # top, the way SES dual-signs. FBL partners dispatch reports based on
    # the DKIM d= domain, which serves all customers from a single FBL
    # registration per partner.
    signing_domains = Domain.objects.select_related(
        "dkim_key_rsa2048",
        "dkim_key_ed25519",
    ).filter(Q(name=settings.RELAY_PLATFORM_DOMAIN) | Q(pk=domain.pk))
    for sign_domain in signing_domains:
        for selector, key in sign_domain.dkim_ciphers:
            signed = add_dkim_signature(
                signed, selector, sign_domain.name, key, INCLUDE_HEADERS
            )
    return signed


def verify_signature(raw_bytes):
    try:
        verified = dkim.verify(raw_bytes)
    except dkim.DKIMException:
        return False, None
    return verified, None


def dkim_txt_lookup(name: bytes, timeout: int = 5) -> bytes | None:
    """
    Return relay's DKIM public key record for a query name, or None.

    Answers `<selector>._domainkey.<domain>` from the Domain models the
    same way the authoritative nameserver does, so a verification verdict
    never depends on the live DNS path. The timeout parameter only exists
    to satisfy dkimpy's dnsfunc protocol.
    """
    query = name.decode("ascii", "replace").strip().rstrip(".").lower()
    selector, separator, domain_name = query.partition("._domainkey.")
    if not separator or not selector or not domain_name:
        return None
    sender_prefix = f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}."
    names = {domain_name}
    if domain_name.startswith(sender_prefix):
        names.add(domain_name.removeprefix(sender_prefix))
    for domain in Domain.objects.filter(name__in=names):
        for cipher_selector, key in domain.dkim_ciphers:
            if cipher_selector == selector and key is not None:
                return dkim_record(key).encode("ascii")
    return None


def parse_signature_tags(value: str) -> dict[str, str]:
    """Return the tag=value pairs of a DKIM-Signature header value."""
    return dict(
        parsed
        for field in value.split(";")
        if "=" in field.strip() and (parsed := field.strip().split("=", 1))
    )


def verify_signatures(raw_bytes: bytes) -> list[dict]:
    """
    Return per-DKIM-Signature verification results for a message.

    Each result carries the signature's tags plus its verification outcome.
    Public keys are answered from relay's own zone data, so a verdict never
    waits on the network. Signatures whose key relay does not publish
    report `permerror` instead of a bare failure.
    """
    if not raw_bytes:
        return []
    results = []
    try:
        msg = message_from_bytes(raw_bytes)
        signatures = [
            value for key, value in msg.items() if key.lower() == "dkim-signature"
        ]
    except ValueError:
        logger.warning("DKIM verification received an unparseable message")
        return []
    for index, value in enumerate(signatures):
        tags = parse_signature_tags(value)
        results.append(
            tags | {"result": verify_signature_at(raw_bytes, index, tags).value}
        )
    return results


def verify_signature_at(
    raw_bytes: bytes, index: int, tags: dict[str, str]
) -> AuthResult:
    """Return the verification outcome of one DKIM signature."""
    if not (tags.get("d") and tags.get("s")):
        return AuthResult.PERMERROR
    name = f"{tags['s']}._domainkey.{tags['d']}".encode("ascii", "replace")
    if dkim_txt_lookup(name) is None:
        return AuthResult.PERMERROR
    try:
        verified = dkim.DKIM(raw_bytes).verify(idx=index, dnsfunc=dkim_txt_lookup)
    except dkim.ValidationError:
        return AuthResult.FAIL
    except dkim.DKIMException, IndexError:
        logger.warning("DKIM verification of signature %d failed", index, exc_info=True)
        return AuthResult.PERMERROR
    return AuthResult.PASS if verified else AuthResult.FAIL
