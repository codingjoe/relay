"""Shared TLS helpers for the mail servers."""

import datetime
import logging
import ssl
import time
from collections.abc import Iterator
from pathlib import Path

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


class MismatchedTlsPathCountsError(ValueError):
    """The certificate and key path lists have different lengths."""

    def __init__(self):
        super().__init__("Got different numbers of certificate and key paths")


def build_tls_context(
    cert_path: str | list[str], key_path: str | list[str]
) -> ssl.SSLContext | None:
    """
    Return a TLS server context, or None when no cert is configured.

    Accept one path pair, or one pair per MX hostname, served by SNI.
    Raises when configured paths cannot be loaded.
    """
    if not cert_path or not key_path:
        return None
    cert_paths = [cert_path] if isinstance(cert_path, str) else cert_path
    key_paths = [key_path] if isinstance(key_path, str) else key_path
    if len(cert_paths) != len(key_paths):
        raise MismatchedTlsPathCountsError
    contexts = {}
    for cert, key in zip(cert_paths, key_paths, strict=True):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert, key)
        for hostname in certificate_hostnames(cert):
            contexts[hostname] = context
    primary = next(iter(contexts.values()))
    if len(contexts) > 1:

        def serve_certificate_by_sni(ssl_socket, server_name, tls_context):
            if server_name:
                context = contexts.get(server_name.lower())
                if context is not None:
                    ssl_socket.context = context

        primary.sni_callback = serve_certificate_by_sni
    return primary


def certificate_hostnames(cert_path: str) -> Iterator[str]:
    """Yield the DNS names a certificate is valid for."""
    certificate = x509.load_pem_x509_certificate(Path(cert_path).read_bytes())
    try:
        san = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
        yield from san.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        yield certificate.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)[
            0
        ].value


def wait_for_certificate_and_key(
    cert_path: str | list[str],
    key_path: str | list[str],
    timeout: datetime.timedelta = datetime.timedelta(minutes=5),
) -> None:
    """
    Block until the certificate and key files load successfully.

    Accept one path pair, or one pair per MX hostname.
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
