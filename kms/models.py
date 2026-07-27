"""Cryptographic signing key storage."""

import dkim

from cryptography.hazmat.primitives import serialization
from django.db import models
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped

from . import keys


class SigningKey(TimeStamped):
    """A cryptographic signing key — algorithm-agnostic and purpose-agnostic.

    The private PEM is Fernet-encrypted at rest via :mod:`kms.keystore`. The
    public PEM is stored in plaintext so verifiers (DNS, HTTP ``whpk_``
    header, …) can fetch it without a decryption key.
    """

    class Algorithm(models.TextChoices):
        RSA_2048 = "rsa-2048", "RSA 2048"
        RSA_1024 = "rsa-1024", "RSA 1024"
        ED25519 = "ed25519", "Ed25519"

    algorithm = models.CharField(
        _("algorithm"),
        max_length=8,
        choices=Algorithm,
        help_text=_("Public-key algorithm and size used to sign."),
    )
    encrypted_private_key = models.TextField(
        _("encrypted private key"),
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
        return keys.load(self.encrypted_private_key).sign(payload)

    def sign_dkim(
        self, message: bytes, selector: str, domain: str, include_headers: list[str]
    ) -> bytes:
        privkey, algo = keys.dkim_key_material(
            self.encrypted_private_key, self.algorithm
        )
        return dkim.sign(
            message,
            selector.encode("ascii"),
            domain.encode("ascii"),
            privkey,
            signature_algorithm=algo,
            include_headers=include_headers,
        )

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

    @classmethod
    def generate(cls, algorithm: str) -> SigningKey:
        pair = keys.generate(algorithm)
        return cls.objects.create(
            algorithm=algorithm,
            encrypted_private_key=pair.ciphertext,
            public_key=pair.public_key_pem,
            key_id=pair.key_id,
        )
