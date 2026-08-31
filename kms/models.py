import dkim
from cryptography.hazmat.primitives import serialization
from django.db import models
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped

from . import certificates, keys


class SigningKey(TimeStamped):
    """A cryptographic signing key. Algorithm-agnostic and purpose-agnostic."""

    class Algorithm(models.TextChoices):
        RSA_2048 = "rsa-2048", "RSA 2048"
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


class Certificate(TimeStamped):
    """A TLS certificate presented by a remote server."""

    fingerprint = models.TextField(
        _("fingerprint"),
        primary_key=True,
        help_text=_("SHA-256 fingerprint of the certificate, as lowercase hex."),
    )
    subject = models.TextField(
        _("subject"),
        blank=True,
        help_text=_("Subject of the certificate, in RFC 4514 notation."),
    )
    subject_alternative_names = models.TextField(
        _("subject alternative names"),
        blank=True,
        help_text=_("DNS names the certificate covers, comma-separated."),
    )
    issuer = models.TextField(
        _("issuer"),
        blank=True,
        help_text=_("Subject of the authority that signed the certificate."),
    )
    serial_number = models.TextField(
        _("serial number"),
        blank=True,
        help_text=_("Serial number of the certificate, as lowercase hex."),
    )
    issuer_certificate = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issued_certificates",
        verbose_name=_("issuer certificate"),
        help_text=_("Certificate that signed this certificate, when presented."),
    )
    not_before = models.DateTimeField(
        _("valid from"),
        null=True,
        blank=True,
        help_text=_("Point in time from which the certificate is valid."),
    )
    not_after = models.DateTimeField(
        _("valid until"),
        null=True,
        blank=True,
        help_text=_("Point in time until which the certificate is valid."),
    )

    def __str__(self):
        return self.subject or f"sha256:{self.fingerprint[:16]}…"

    @property
    def chain(self) -> list[Certificate]:
        """Return this certificate and its presented issuers, leaf first."""
        certificates = [self]
        while len(certificates) < 10 and certificates[-1].issuer_certificate:
            certificates.append(certificates[-1].issuer_certificate)
        return certificates

    @classmethod
    def store_presented_chain(cls, parsed_certificates) -> Certificate:
        """Store the certificates a server presented and return the leaf row."""
        stored_certificates = [
            cls.objects.get_or_create(
                fingerprint=certificates.format_fingerprint(parsed_certificate),
                defaults={
                    "subject": parsed_certificate.subject.rfc4514_string(),
                    "subject_alternative_names": (
                        certificates.format_subject_alternative_names(
                            parsed_certificate
                        )
                    ),
                    "issuer": parsed_certificate.issuer.rfc4514_string(),
                    "serial_number": format(parsed_certificate.serial_number, "x"),
                    "not_before": parsed_certificate.not_valid_before_utc,
                    "not_after": parsed_certificate.not_valid_after_utc,
                },
            )[0]
            for parsed_certificate in parsed_certificates
        ]
        for certificate, issuer_certificate in zip(
            stored_certificates, [*stored_certificates[1:], None]
        ):
            if certificate.issuer_certificate != issuer_certificate:
                certificate.issuer_certificate = issuer_certificate
                certificate.save(update_fields=["issuer_certificate", "modified_at"])
        return stored_certificates[0]
