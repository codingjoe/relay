"""DKIM signing and verification for outbound messages."""

import logging

import dkim
from cryptography.hazmat.primitives import serialization
from django.conf import settings

from kms import keys
from kms.models import SigningKey

logger = logging.getLogger(__name__)

INCLUDE_HEADERS = ["From", "To", "Subject", "Date", "Message-ID"]
PLATFORM_INCLUDE_HEADERS = [*INCLUDE_HEADERS, "Feedback-ID"]

PLATFORM_PRIVATE_KEY_SETTINGS = (
    (
        "rsa2048",
        "RELAY_DKIM_PLATFORM_RSA2048_PRIVATE_KEY",
        SigningKey.Algorithm.RSA_2048,
    ),
    (
        "rsa1024",
        "RELAY_DKIM_PLATFORM_RSA1024_PRIVATE_KEY",
        SigningKey.Algorithm.RSA_1024,
    ),
    (
        "ed25519",
        "RELAY_DKIM_PLATFORM_ED25519_PRIVATE_KEY",
        SigningKey.Algorithm.ED25519,
    ),
)


class PlatformSigningKey:
    """A DKIM key for the platform sending domain, configured via settings."""

    def __init__(self, algorithm: str, private_pem: str):
        self.algorithm = algorithm
        self.private_pem = private_pem
        self.public_key = keys.public_pem_from_private(private_pem)

    def public_bytes_raw(self) -> bytes:
        return keys.load_public_pem(self.public_key).public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def public_bytes_der(self) -> bytes:
        return keys.load_public_pem(self.public_key).public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def sign_dkim(
        self, message: bytes, selector: str, domain: str, include_headers: list[str]
    ) -> bytes:
        privkey, signature_algorithm = keys.dkim_key_material_from_pem(
            self.private_pem, self.algorithm
        )
        return dkim.sign(
            message,
            selector.encode("ascii"),
            domain.encode("ascii"),
            privkey,
            signature_algorithm=signature_algorithm,
            include_headers=include_headers,
        )


def platform_dkim_ciphers():
    """Yield (selector, key) pairs for every configured platform key."""
    prefix = settings.RELAY_DNS_DKIM_IDENTIFIER
    for name, setting, algorithm in PLATFORM_PRIVATE_KEY_SETTINGS:
        private_pem = getattr(settings, setting)
        if private_pem:
            try:
                key = PlatformSigningKey(algorithm, private_pem)
            except ValueError:
                logger.exception("Invalid DKIM private key in %r", setting)
            else:
                yield (f"{prefix}-platform-{name}", key)


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
    # Sign for the platform sending domain first. Signatures are prepended,
    # so the customer's signature ends up on top, the way SES dual-signs.
    # FBL partners dispatch reports based on the DKIM d= domain, which lets
    # us serve all customers from a single FBL registration per partner.
    for selector, key in platform_dkim_ciphers():
        signed = add_dkim_signature(
            signed,
            selector,
            settings.RELAY_PLATFORM_DOMAIN,
            key,
            PLATFORM_INCLUDE_HEADERS,
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
