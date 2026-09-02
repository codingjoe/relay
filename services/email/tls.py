"""Shared TLS helpers for the mail servers."""

import datetime
import logging
import ssl
import time
from collections.abc import Iterator

from cryptography import x509

logger = logging.getLogger(__name__)


class MissingTlsCertificateError(ValueError):
    """Implicit TLS ports are configured but no certificate paths are set."""

    def __init__(self):
        super().__init__("Implicit TLS ports require a TLS certificate")


class CertificateLoadTimeoutError(TimeoutError):
    """The TLS certificate and key files did not load within the timeout."""

    def __init__(self, cert_path, key_path, timeout):
        super().__init__(
            f"TLS certificate ({cert_path}) and key ({key_path}) "
            f"did not load within {timeout}."
        )


def build_tls_context(cert_path: str, key_path: str) -> ssl.SSLContext | None:
    """
    Return a TLS server context, or None when no cert is configured.

    Raises when cert paths are configured but cannot be loaded, so a
    misconfigured production server fails at startup instead of silently
    serving plaintext.
    """
    if not cert_path or not key_path:
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    return context


def wait_for_certificate_and_key(
    cert_path: str,
    key_path: str,
    timeout: datetime.timedelta = datetime.timedelta(minutes=5),
) -> None:
    """
    Block until the certificate and key files load successfully.

    Raise TimeoutError if the files do not load within timeout.
    Return immediately when no TLS paths are configured.
    """
    if cert_path and key_path:
        deadline = time.monotonic() + timeout.total_seconds()
        logged = False
        while True:
            try:
                build_tls_context(cert_path, key_path)
            except OSError:
                if time.monotonic() > deadline:
                    raise CertificateLoadTimeoutError(cert_path, key_path, timeout)
                if not logged:
                    logger.warning(
                        "Waiting for TLS certificate (%s) and key (%s)…",
                        cert_path,
                        key_path,
                    )
                    logged = True
                else:
                    logger.debug(
                        "Waiting for TLS certificate (%s) and key (%s)…",
                        cert_path,
                        key_path,
                    )
                time.sleep(5)
            else:
                logger.info("TLS certificate and key are available.")
                return


def parse_peer_certificates(
    ssl_object: ssl.SSLObject,
) -> Iterator[x509.Certificate]:
    """Yield the X.509 certificates the remote server presented."""
    chain = ssl_object.get_unverified_chain() or ssl_object.get_verified_chain() or ()
    for der in chain:
        yield x509.load_der_x509_certificate(der)
