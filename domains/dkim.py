"""DKIM signing and verification for outbound messages."""

import logging

import dkim
from django.conf import settings
from django.db.models import Q

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
    """Sign a message with DKIM for the sender domain, plus the domain named
    RELAY_PLATFORM_DOMAIN when it exists.

    Raise ValueError when a signing domain is missing a key, because
    quietly sending unsigned mail would fail DMARC and hurt deliverability.
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
            if key is None:
                raise ValueError(
                    f"Domain {sign_domain.name} has no DKIM signing key "
                    f"for selector {selector}."
                )
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
