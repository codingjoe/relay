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
    """Sign a message with DKIM for the sender domain, plus the domain named
    RELAY_PLATFORM_DOMAIN when it exists."""
    signed = raw_bytes
    # Signatures are prepended, so the customer's signature ends up on
    # top, the way SES dual-signs. FBL partners dispatch reports based on
    # the DKIM d= domain, which serves all customers from a single FBL
    # registration per partner.
    try:
        platform_domains = (
            Domain.objects.select_related(
                "dkim_key_rsa2048",
                "dkim_key_rsa1024",
                "dkim_key_ed25519",
            )
            .filter(name=canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN))
            .exclude(pk=domain.pk)
        )
    except ValidationError:
        platform_domains = Domain.objects.none()
    for sign_domain in [*platform_domains, domain]:
        for selector, key in sign_domain.dkim_ciphers:
            if key:
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
