"""DKIM signing and verification for outbound messages."""

import logging

import dkim

logger = logging.getLogger(__name__)

INCLUDE_HEADERS = ["From", "To", "Subject", "Date", "Message-ID"]


def sign_message(raw_bytes, domain):
    """Sign a message with DKIM using every cipher the domain has a key for."""
    signed = raw_bytes
    for selector, key in domain.dkim_ciphers:
        if key is None:
            continue
        try:
            sig = key.sign_dkim(signed, selector, domain.name, INCLUDE_HEADERS)
            signed = sig + signed
        except dkim.DKIMException as e:
            logger.error(f"DKIM signing failed for {domain.name} ({selector}): {e}")
    return signed


def verify_signature(raw_bytes):
    try:
        verified = dkim.verify(raw_bytes)
    except dkim.DKIMException:
        return False, None
    return verified, None
