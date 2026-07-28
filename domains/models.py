import secrets
import string
from functools import reduce
from operator import or_

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from kms.models import SigningKey


class DomainQuerySet(models.QuerySet):
    def root_for(self, name):
        parts = name.lower().split(".")
        candidates = [".".join(parts[i:]) for i in range(len(parts))]
        return self.filter(
            reduce(or_, (models.Q(name__iexact=c) for c in candidates)),
            org__isnull=False,
        )


def generate_verification_token():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(16))


class Domain(TimeStamped):
    """Root domain — verified once with NS delegation, DMARC, SPF, and DKIM."""

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

    class Meta(TimeStamped.Meta):
        indexes = [
            models.Index(Lower("name"), name="domain_name_lower_idx"),
        ]

    objects = models.Manager.from_queryset(DomainQuerySet)()

    def get_absolute_url(self):
        if self.org is None:
            return None
        return reverse(
            "domains:domain-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    def save(self, *args, **kwargs):
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
    def dkim_ciphers(self):
        prefix = settings.RELAY_DNS_DKIM_IDENTIFIER
        return [
            (f"{prefix}-rsa2048", self.dkim_key_rsa2048),
            (f"{prefix}-rsa1024", self.dkim_key_rsa1024),
            (f"{prefix}-ed25519", self.dkim_key_ed25519),
        ]

    @property
    def sender_domain(self):
        return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{self.name}"

    @property
    def dmarc_record_name(self):
        return f"_dmarc.{self.name}"

    def dkim_cname_for_selector(self, selector: str) -> tuple[str, str]:
        base = self.name if self.is_system else self.sender_domain
        name = f"{selector}._domainkey.{self.name}"
        target = f"{selector}._domainkey.{base}"
        return name, target

    @property
    def dkim_cnames(self):
        return [
            self.dkim_cname_for_selector(selector) for selector, _ in self.dkim_ciphers
        ]

    @property
    def spf_record(self):
        return "v=spf1 a mx ~all"

    @property
    def root_spf_record(self):
        return f"v=spf1 include:{self.sender_domain} ~all"

    @property
    def return_path_domain(self):
        return f"{settings.RELAY_DNS_CUSTOM_RETURN_PATH_PREFIX}.{self.sender_domain}"

    @property
    def verification_record_name(self):
        return f"{settings.RELAY_DNS_DOMAIN_VERIFY_PREFIX}.{self.sender_domain}"

    @property
    def verification_record(self):
        return f"{settings.RELAY_DNS_DOMAIN_VERIFY_PREFIX} {self.verification_token}"

    @property
    def dmarc_reporting_address(self):
        return f"{settings.RELAY_DMARC_REPORT_LOCAL_PART}@{self.sender_domain}"

    @property
    def dmarc_ruf_reporting_address(self):
        return f"{settings.RELAY_DMARC_RUF_LOCAL_PART}@{self.sender_domain}"

    @property
    def tls_reporting_address(self):
        return f"{settings.RELAY_TLS_REPORT_LOCAL_PART}@{self.sender_domain}"

    @property
    def dmarc_record(self):
        """DMARC record for the root domain, with rua/ruf pointing to the sender subdomain."""
        return (
            f"v=DMARC1; p=none; sp=none; adkim=r; aspf=r;"
            f" rua=mailto:{self.dmarc_reporting_address};"
            f" ruf=mailto:{self.dmarc_ruf_reporting_address};"
        )

    @property
    def tls_rpt_record(self):
        """TLS-RPT record for the root domain, with rua pointing to the sender subdomain."""
        return f"v=TLSRPTv1;rua=mailto:{self.tls_reporting_address}"

    @property
    def sender_dmarc_record(self):
        """DMARC record served at _dmarc.{sender_subdomain} for external reporting authorization."""
        return "v=DMARC1; p=none"

    @property
    def sender_tls_rpt_record(self):
        """TLS-RPT record served at _smtp._tls.{sender_subdomain}."""
        return f"v=TLSRPTv1;rua=mailto:{self.tls_reporting_address}"
