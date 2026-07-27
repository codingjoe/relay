"""Cryptographic key storage in the ``kms`` app.

The ``SigningKey`` model is the cryptographic primitive. It knows an
algorithm, a public PEM, and a Fernet-encrypted private PEM. It exposes
only three operations: generate a key, return the public key, and sign
payloads. Private key material never leaves the ``kms`` app.
"""

from cryptography.hazmat.primitives import serialization
from django.db import models
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped

from . import keys


def _load_public_pem(public_key: str):
    """Return the in-memory public key object from a PEM string."""
    return serialization.load_pem_public_key(public_key.encode())


class SigningKey(TimeStamped):
    """A cryptographic signing key — algorithm-agnostic and purpose-agnostic.

    The private PEM is Fernet-encrypted at rest via :mod:`kms.keystore`. The
    public PEM is stored in plaintext so verifiers (DNS, HTTP ``whpk_``
    header, …) can fetch it without a decryption key.
    """

    class Algorithm(models.TextChoices):
        RSA_2048 = "rsa-2048", _("RSA 2048")
        RSA_1024 = "rsa-1024", _("RSA 1024")
        ED25519 = "ed25519", _("Ed25519")

    algorithm = models.CharField(
        _("algorithm"),
        max_length=8,
        choices=Algorithm,
        help_text=_("Public-key algorithm and size used to sign."),
    )
    private_key = models.TextField(
        _("private key"),
        help_text=_("Fernet-encrypted PKCS#8 PEM."),
    )
    public_key = models.TextField(
        _("public key"),
        help_text=_("Plaintext public PEM — shareable with verifiers."),
    )
    key_id = models.CharField(
        _("key ID"),
        max_length=16,
        editable=False,
        help_text=_("Short SHA256 fingerprint of the public key."),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["algorithm", "key_id"],
                name="unique_signing_key_id_per_algorithm",
            ),
        ]

    def __str__(self):
        return f"{self.algorithm}/{self.key_id}"

    def sign(self, payload: bytes) -> bytes:
        """Sign ``payload`` with the private key and return the raw signature bytes."""
        return keys.load(self.private_key).sign(payload)

    def public_bytes_raw(self) -> bytes:
        """Return the raw public key bytes (used for Standard Webhooks ``whpk_``)."""
        return _load_public_pem(self.public_key).public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def public_bytes_der(self) -> bytes:
        """Return the SubjectPublicKeyInfo DER encoding (used for DKIM ``p=``)."""
        return _load_public_pem(self.public_key).public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @classmethod
    def generate(cls, algorithm: str) -> SigningKey:
        """Generate a new key for the given algorithm and persist it."""
        pair = keys.generate(algorithm)
        return cls.objects.create(
            algorithm=algorithm,
            private_key=pair.ciphertext,
            public_key=pair.public_key_pem,
            key_id=pair.key_id,
        )
