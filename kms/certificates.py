"""Helpers for X.509 certificates presented by remote servers."""

from cryptography import x509


def format_subject_alternative_names(certificate) -> str:
    """Return the DNS names a certificate covers, comma-separated."""
    try:
        extension = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
    except x509.ExtensionNotFound:
        return ""
    return ", ".join(extension.value.get_values_for_type(x509.DNSName))
