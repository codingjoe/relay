"""DKIM signing and verification for outbound messages."""

import logging

import dkim
from django.conf import settings

from .models import Domain

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
    """Sign a message with DKIM using every cipher that has an available key."""
    signed = raw_bytes
    # Cosign with the platform domain, the Domain row named
    # RELAY_PLATFORM_DOMAIN. A missing row or missing keys skips the
    # cosign, and relay never cosigns when the signing domain already is
    # the platform domain. Signatures are prepended, so the customer's
    # signature ends up on top, the way SES dual-signs. FBL partners
    # dispatch reports based on the DKIM d= domain, which lets us serve
    # all customers from a single FBL registration per partner.
    try:
        platform_domain = Domain.objects.get(
            name__iexact=settings.RELAY_PLATFORM_DOMAIN
        )
    except Domain.DoesNotExist:
        platform_domain = None
    if platform_domain and platform_domain.pk != domain.pk:
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
