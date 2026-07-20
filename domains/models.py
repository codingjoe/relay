import base64
import secrets
import string

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


def generate_dkim_identifier_string():
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def generate_verification_token():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


def generate_rsa_private_key(key_size=2048):
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
    )
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("ascii")


class DkimKey(TimeStamped):
    class KeyType(models.TextChoices):
        RSA_2048 = "rsa2048", _("RSA 2048")
        RSA_1024 = "rsa1024", _("RSA 1024")
        ED25519 = "ed25519", _("Ed25519")

    domain = models.ForeignKey(
        "Domain",
        on_delete=models.CASCADE,
        related_name="dkim_keys",
    )
    key_type = models.CharField(
        _("key type"),
        max_length=8,
        choices=KeyType,
        help_text=_("Algorithm and size for this DKIM key."),
    )
    private_key = models.TextField(
        _("private key"),
        help_text=_("PEM-encoded key used for DKIM signing."),
    )
    selector = models.CharField(
        _("selector"),
        max_length=6,
        help_text=_("DKIM selector in the DNS record name."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Only active keys sign and are served in DNS."),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "selector"],
                name="unique_dkim_selector_per_domain",
            ),
        ]

    def __str__(self):
        return f"{self.domain} / {self.key_type} / {self.selector}"


class Domain(TimeStamped):
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
        help_text=_("Sender domain, e.g. example.com."),
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
        help_text=_("NS delegation check result."),
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
        help_text=_("SPF record check result."),
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
        help_text=_("DKIM CNAME check result."),
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
        help_text=_("DMARC record check result."),
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
    outgoing = models.BooleanField(
        _("outgoing"),
        default=True,
        help_text=_("Allow sending from this domain."),
    )
    incoming = models.BooleanField(
        _("incoming"),
        default=True,
        help_text=_("Allow receiving for this domain."),
    )

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        if self.org is None:
            return None
        return reverse(
            "domains:domain_detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.dkim_keys.exists():
            DkimKey.objects.create(
                domain=self,
                key_type=DkimKey.KeyType.RSA_2048,
                private_key=generate_rsa_private_key(2048),
                selector=generate_dkim_identifier_string(),
            )

    @property
    def is_verified(self):
        return self.verified_at is not None

    @property
    def is_system(self):
        return self.org is None

    @property
    def active_dkim_key(self):
        return self.dkim_keys.filter(is_active=True).first()

    @property
    def dkim_private_key(self):
        key = self.active_dkim_key
        return key.private_key if key else ""

    @property
    def dkim_identifier_string(self):
        key = self.active_dkim_key
        return key.selector if key else ""

    @property
    def sender_domain(self):
        """Return the sender subdomain our nameserver serves."""
        return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{self.name}"

    @property
    def dkim_signing_domain(self):
        """Return the root domain used as the DKIM d= tag."""
        return self.name

    @property
    def dmarc_record_name(self):
        return f"_dmarc.{self.name}"

    @property
    def dkim_public_key_b64(self):
        private_key = serialization.load_pem_private_key(
            self.dkim_private_key.encode("ascii"),
            password=None,
        )
        public_key = private_key.public_key()
        der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return base64.b64encode(der).decode("ascii")

    @property
    def dkim_selector(self):
        return f"{settings.RELAY_DNS_DKIM_IDENTIFIER}-{self.dkim_identifier_string}"

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
        return f"v=DKIM1; t=s; h=sha256; p={self.dkim_public_key_b64};"

    @property
    def spf_record(self):
        return f"v=spf1 a mx include:{settings.RELAY_DNS_SPF_INCLUDE} ~all"

    @property
    def return_path_domain(self):
        return f"{settings.RELAY_DNS_CUSTOM_RETURN_PATH_PREFIX}.{self.sender_domain}"

    @property
    def verification_record_name(self):
        return f"{settings.RELAY_DNS_DOMAIN_VERIFY_PREFIX}.{self.sender_domain}"

    @property
    def verification_record(self):
        return f"{settings.RELAY_DNS_DOMAIN_VERIFY_PREFIX} {self.verification_token}"
