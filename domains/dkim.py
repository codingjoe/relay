"""DKIM signing and verification for outbound messages."""

import logging

import dkim

logger = logging.getLogger(__name__)


def sign_message(raw_bytes, domain):
    """Sign a message with DKIM using the domain's active private key.

    Returns the signed message bytes, or the original bytes if signing fails.
    """
    try:
        private_key = domain.dkim_private_key.encode("ascii")
        selector = domain.dkim_selector
        domain_name = domain.dkim_signing_domain

        sig = dkim.sign(
            raw_bytes,
            selector.encode("ascii"),
            domain_name.encode("ascii"),
            private_key,
            include_headers=["From", "To", "Subject", "Date", "Message-ID"],
        )
        return sig
    except Exception as e:
        logger.error(f"DKIM signing failed for domain {domain.name}: {e}")
        return raw_bytes


def verify_signature(raw_bytes):
    """Verify a DKIM signature on a message.

    Returns (verified: bool, domain: str or None).
    """
    try:
        verified = dkim.verify(raw_bytes)
        return verified, None
    except Exception:
        return False, None
