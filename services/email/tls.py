"""Shared TLS helpers for the mail servers."""

import ssl


def build_tls_context(cert_path: str, key_path: str) -> ssl.SSLContext | None:
    """Return a TLS server context, or None when no cert is configured.

    Raises when cert paths are configured but cannot be loaded, so a
    misconfigured production server fails at startup instead of silently
    serving plaintext.
    """
    if not cert_path or not key_path:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context
