"""DKIM signing and verification for outbound messages."""

import logging

import dkim
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Domain, canonicalize_domain_name

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
    """Sign a message with DKIM for the signing domain, then cosign with the
    platform domain when its Domain row exists and the signer is another domain."""
    signed = raw_bytes
    # Cosigning lets FBL partners dispatch reports based on the DKIM d=
    # domain, which serves all customers from a single FBL registration
    # per partner. Signatures are prepended, so the customer's signature
    # ends up on top, the way SES dual-signs.
    try:
        platform_domain = Domain.objects.select_related(
            "dkim_key_rsa2048",
            "dkim_key_rsa1024",
            "dkim_key_ed25519",
        ).get(
            name=canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN),
            is_platform=True,
        )
    except Domain.DoesNotExist, ValidationError:
        platform_domain = None
    if platform_domain and domain.name != platform_domain.name:
        for selector, key in platform_domain.dkim_ciphers:
            if key:
                signed = add_dkim_signature(
                    signed, selector, platform_domain.name, key, INCLUDE_HEADERS
                )
    for selector, key in domain.dkim_ciphers:
        if key:
            signed = add_dkim_signature(
                signed, selector, domain.name, key, INCLUDE_HEADERS
            )
    return signed


def verify_signature(raw_bytes):
    try:
        verified = dkim.verify(raw_bytes)
    except dkim.DKIMException:
        return False, None
    return verified, None
