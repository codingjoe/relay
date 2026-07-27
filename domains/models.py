import secrets
import string

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


class DomainQuerySet(models.QuerySet):
    def root_for(self, name):
        """Filter to root Domains that own ``name`` (exact match or parent suffix).

        Strips subdomain labels one at a time until an owned root is found.
        Returns the queryset — chain ``.get()`` to fetch one or raise.
        """
        rcpt_lower = name.lower()
        parts = rcpt_lower.split(".")
        candidates = [".".join(parts[i:]) for i in range(len(parts))]
        return self.filter(name__iexact=candidates, org__isnull=False)


DomainManager = models.Manager.from_queryset(DomainQuerySet)


def generate_verification_token():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


class Domain(TimeStamped):
    """Root domain — verified once with NS delegation, DMARC, SPF, and DKIM.

    Uses relaxed DMARC alignment (``adkim=r``, ``aspf=r``) so email from
    any subdomain (e.g. ``app.acme.com``) is signed with ``d=acme.com``
    and still passes DMARC.
    """

    class VerificationMethod(models.TextChoices):
        DNS = "dns", _("DNS")
        EMAIL = "email", _("email")

    class Status(models.TextChoices):
        OK = "ok", _("ok")
        ERROR = "error", _("error")
        PENDING = "pending", _("pending")
        UNCHECKED = "unchecked", _("unchecked")

    name = models.CharField(
        _("name"),
        max_length=255,
        unique=True,
        help_text=_("Root domain, e.g. acme.com."),
    )
    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="domains",
        null=True,
        blank=True,
        help_text=_("Owning organization; null for system domains."),
    )
    verification_token = models.CharField(
        _("verification token"),
        max_length=16,
        default=generate_verification_token,
        editable=False,
        help_text=_("Token published in DNS to prove ownership."),
    )
    verified_at = models.DateTimeField(
        _("verified at"),
        null=True,
        blank=True,
        help_text=_("When DNS verification completed."),
    )
    nameserver_status = models.CharField(
        _("nameserver status"),
        max_length=9,
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("NS delegation check result for the sender subdomain."),
    )
    nameserver_error = models.TextField(
        _("nameserver error"),
        blank=True,
        help_text=_("Failure detail if NS delegation is incorrect."),
    )
    spf_status = models.CharField(
        _("SPF status"),
        max_length=9,
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("SPF record check result on the root domain."),
    )
    spf_error = models.TextField(
        _("SPF error"),
        blank=True,
        help_text=_("Failure detail if the SPF record is incorrect."),
    )
    dkim_status = models.CharField(
        _("DKIM status"),
        max_length=9,
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("DKIM CNAME check result on the root domain."),
    )
    dkim_error = models.TextField(
        _("DKIM error"),
        blank=True,
        help_text=_("Failure detail if the DKIM CNAME is incorrect."),
    )
    dmarc_status = models.CharField(
        _("DMARC status"),
        max_length=9,
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("DMARC record check result on the root domain."),
    )
    dmarc_error = models.TextField(
        _("DMARC error"),
        blank=True,
        help_text=_("Failure detail if the DMARC record is incorrect."),
    )
    dns_checked_at = models.DateTimeField(
        _("DNS checked at"),
        null=True,
        blank=True,
        help_text=_("Last DNS check timestamp."),
    )

    dkim_key_rsa2048 = models.ForeignKey(
        "kms.SigningKey",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text=_("RSA-2048 DKIM signing key."),
    )
    dkim_key_rsa1024 = models.ForeignKey(
        "kms.SigningKey",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text=_(
            "RSA-1024 DKIM signing key — for compatibility with older verifiers."
        ),
    )
    dkim_key_ed25519 = models.ForeignKey(
        "kms.SigningKey",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
        help_text=_("Ed25519 DKIM signing key."),
    )

    def __str__(self):
        return self.name

    objects = DomainManager()

    def get_absolute_url(self):
        if self.org is None:
            return None
        return reverse(
            "domains:domain-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    def save(self, *args, **kwargs):
        from kms.models import SigningKey

        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.org is not None and self.dkim_key_rsa2048_id is None:
            self.dkim_key_rsa2048 = SigningKey.generate(SigningKey.Algorithm.RSA_2048)
            self.dkim_key_rsa1024 = SigningKey.generate(SigningKey.Algorithm.RSA_1024)
            self.dkim_key_ed25519 = SigningKey.generate(SigningKey.Algorithm.ED25519)
            super().save(
                update_fields=[
                    "dkim_key_rsa2048",
                    "dkim_key_rsa1024",
                    "dkim_key_ed25519",
                ]
            )

    @property
    def is_verified(self):
        return self.verified_at is not None

    @property
    def is_system(self):
        return self.org is None

    @property
    def primary_dkim_key(self):
        """Return the RSA-2048 key used to sign outbound mail."""
        return self.dkim_key_rsa2048

    @property
    def dkim_ciphers(self):
        """Return all DKIM signing keys in DNS-served order."""
        return [
            ("rsa2048", self.dkim_key_rsa2048),
            ("rsa1024", self.dkim_key_rsa1024),
            ("ed25519", self.dkim_key_ed25519),
        ]

    @property
    def dkim_private_key(self):
        """Return the decrypted RSA-2048 PEM, ready for the DKIM library."""
        from kms import keys as kms_keys

        return (
            kms_keys.decrypt(self.dkim_key_rsa2048.private_key)
            if self.dkim_key_rsa2048
            else ""
        )

    @property
    def sender_domain(self):
        """Return the sender subdomain zone apex our nameserver serves."""
        return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{self.name}"

    @property
    def dkim_signing_domain(self):
        """Return the root domain used as the DKIM ``d=`` tag by default."""
        return self.name

    @property
    def dmarc_record_name(self):
        """Return the ``_dmarc.<name>`` record name our nameserver serves."""
        return f"_dmarc.{self.name}"

    @property
    def dkim_public_key_b64(self):
        """Return the base64-encoded RSA-2048 public key for the DKIM ``p=`` tag."""
        import base64

        key = self.primary_dkim_key
        return base64.b64encode(key.public_bytes_der()).decode() if key else ""

    @property
    def dkim_selector(self):
        """Return the selector of the primary RSA-2048 DKIM key."""
        return f"{settings.RELAY_DNS_DKIM_IDENTIFIER}-rsa2048"

    @property
    def dkim_record_name(self):
        """Return the record name our nameserver serves the DKIM public key at."""
        base = self.name if self.is_system else self.sender_domain
        return f"{self.dkim_selector}._domainkey.{base}"

    @property
    def dkim_cname_name(self):
        """Return the CNAME record name the user adds on the root domain."""
        return f"{self.dkim_selector}._domainkey.{self.name}"

    @property
    def dkim_cname_target(self):
        """Return the target the DKIM CNAME points to on our nameserver."""
        return self.dkim_record_name

    @property
    def dkim_record(self):
        """Return the DKIM TXT record value served by our nameserver."""
        return f"v=DKIM1; t=s; h=sha256; p={self.dkim_public_key_b64};"

    def dkim_cname_for_selector(self, selector: str) -> tuple[str, str]:
        """Return the ``(cname_name, cname_target)`` pair for a specific DKIM selector."""
        base = self.name if self.is_system else self.sender_domain
        name = f"{selector}._domainkey.{self.name}"
        target = f"{selector}._domainkey.{base}"
        return name, target

    @property
    def dkim_cnames(self):
        """Return all DKIM ``(cname_name, cname_target)`` pairs, one per cipher."""
        return [
            self.dkim_cname_for_selector(selector) for selector, _ in self.dkim_ciphers
        ]

    @property
    def spf_record(self):
        """Return the SPF record served at the sender subdomain by our nameserver."""
        return "v=spf1 a mx ~all"

    @property
    def root_spf_record(self):
        """Return the SPF record the user adds on their root domain."""
        return f"v=spf1 include:{self.sender_domain} ~all"

    @property
    def return_path_domain(self):
        """Return the custom return-path subdomain zone apex our nameserver serves."""
        return f"{settings.RELAY_DNS_CUSTOM_RETURN_PATH_PREFIX}.{self.sender_domain}"

    @property
    def verification_record_name(self):
        """Return the verification record name our nameserver serves."""
        return f"{settings.RELAY_DNS_DOMAIN_VERIFY_PREFIX}.{self.sender_domain}"

    @property
    def verification_record(self):
        """Return the verification TXT record value served by our nameserver."""
        return f"{settings.RELAY_DNS_DOMAIN_VERIFY_PREFIX} {self.verification_token}"
