import dkim
from cryptography.hazmat.primitives import serialization
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped

from . import keys


class SigningKey(TimeStamped):
    """A cryptographic signing key. Algorithm-agnostic and purpose-agnostic."""

    class Algorithm(models.TextChoices):
        RSA_2048 = "rsa-2048", "RSA 2048"
        RSA_1024 = "rsa-1024", "RSA 1024"
        ED25519 = "ed25519", "Ed25519"

    algorithm = models.TextField(
        _("algorithm"),
        choices=Algorithm,
        help_text=_("Public-key algorithm and size used to sign."),
    )
    encrypted_private_key = models.TextField(
        _("encrypted private key"),
        help_text=_("Fernet-encrypted PKCS#8 PEM."),
    )
    public_key = models.TextField(
        _("public key"),
        help_text=_("Plaintext public PEM. Shareable with verifiers."),
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


class OrgEncryptionKey(TimeStamped):
    """Store an organization's X25519 public key for envelope encryption.

    The server uses this public key to seal file keys. The corresponding
    private key is never stored server-side. It is distributed to org
    members and webhook applications as sealed copies (encrypted with each
    recipient's own public key).
    """

    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="encryption_keys",
    )
    public_key = models.TextField(
        _("public key"),
        help_text=_("Base64-encoded X25519 public key used to seal file keys."),
    )
    key_id = models.CharField(
        _("key ID"),
        max_length=16,
        editable=False,
        help_text=_("Short SHA256 fingerprint of the public key."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Only the active key is used to seal new file keys."),
    )
    recovery_sealed_org_private_key = models.TextField(
        _("recovery sealed org private key"),
        blank=True,
        help_text=_(
            "Org private key encrypted with a KEK derived from a BIP39 "
            "mnemonic. Used for break-glass recovery. Format: base64 of "
            "salt + nonce + ciphertext."
        ),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["org", "key_id"],
                name="unique_org_encryption_key_id_per_org",
            ),
            models.UniqueConstraint(
                fields=["org"],
                condition=models.Q(is_active=True),
                name="unique_active_org_encryption_key_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.org} / {self.key_id}{' (active)' if self.is_active else ''}"

    def save(self, *args, **kwargs):
        if not self.key_id:
            from kms import envelope

            self.key_id = envelope.key_fingerprint(envelope.decode_key(self.public_key))
        super().save(*args, **kwargs)


class RecoveryEvent(TimeStamped):
    """Record each break-glass recovery of the org private key.

    This is a permanent, append-only audit log. Every time someone enters
    the BIP39 mnemonic to recover the org private key, a row is created
    here and all org members are notified. The notification is the
    deterrent: a rogue admin can use the seed on their own machine, but
    cannot prevent the server from logging the event and emailing every
    member.
    """

    org_encryption_key = models.ForeignKey(
        OrgEncryptionKey,
        on_delete=models.CASCADE,
        related_name="recovery_events",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_("User who entered the recovery mnemonic."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.org_encryption_key.org} / {self.triggered_by} / {self.created_at}"
        )
