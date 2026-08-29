from functools import reduce
from operator import or_

import idna
import validators as domain_validators
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Length, Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from kms.models import SigningKey


def canonicalize_domain_name(value):
    """Return the lowercase ASCII UTS-46 form of a domain name."""
    try:
        return idna.encode(value, uts46=True, std3_rules=True).decode("ascii").lower()
    except (idna.IDNAError, UnicodeError) as error:
        raise ValidationError(
            _("Enter a valid domain name, for example acme.com")
        ) from error


def validate_domain_name(value):
    """Validate that *value* is a syntactically valid domain name."""
    if domain_validators.domain(canonicalize_domain_name(value)) is not True:
        raise ValidationError(_("Enter a valid domain name, for example acme.com"))


class DomainQuerySet(models.QuerySet):
    def root_for(self, name, *, include_managed):
        """Return the closest registered parent domain for *name*.

        If more than one ancestor domain exists, the most specific
        name has priority.

        Raises:
            DoesNotExist: If no matching domain is found.
        """
        try:
            parts = idna.uts46_remap(
                name,
                std3_rules=False,
                transitional=False,
            ).split(".")
        except (idna.IDNAError, UnicodeError) as error:
            raise self.model.DoesNotExist from error
        candidates = []
        for index in range(len(parts)):
            try:
                candidate = canonicalize_domain_name(".".join(parts[index:]))
            except ValidationError:
                candidate = None
            if candidate is not None:
                candidates.append(candidate)
        if not candidates:
            raise self.model.DoesNotExist
        qs = self.filter(
            reduce(or_, (models.Q(name__iexact=c) for c in candidates)),
        )
        if not include_managed:
            qs = qs.filter(is_managed=False)
        domains = list(qs.select_related("org").order_by(Length("name").desc()))
        # The platform domain is by design the ancestor of every managed
        # sender domain, so it may share an ancestor chain with domains
        # owned by other organizations without making the match ambiguous.
        if len({domain.org_id for domain in domains}) > 1:
            platform_name = canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN)
            domains = [domain for domain in domains if domain.name != platform_name]
        if not domains or len({domain.org_id for domain in domains}) > 1:
            raise self.model.DoesNotExist
        return domains[0]


class Domain(TimeStamped):
    """Root domain. Verified once with NS delegation, DMARC, SPF, and DKIM."""

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
        validators=[validate_domain_name],
        help_text=_("Root domain, for example acme.com."),
    )
    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="domains",
        help_text=_("Owning organization."),
    )
    verified_at = models.DateTimeField(
        _("verified at"),
        null=True,
        blank=True,
        help_text=_("When DNS verification completed."),
    )
    nameserver_status = models.TextField(
        _("nameserver status"),
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("NS delegation check result for the sender subdomain."),
    )
    nameserver_error = models.TextField(
        _("nameserver error"),
        blank=True,
        help_text=_("Failure detail if NS delegation is incorrect."),
    )
    spf_status = models.TextField(
        _("SPF status"),
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("SPF record check result on the root domain."),
    )
    spf_error = models.TextField(
        _("SPF error"),
        blank=True,
        help_text=_("Failure detail if the SPF record is incorrect."),
    )
    dkim_status = models.TextField(
        _("DKIM status"),
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("DKIM CNAME check result on the root domain."),
    )
    dkim_error = models.TextField(
        _("DKIM error"),
        blank=True,
        help_text=_("Failure detail if the DKIM CNAME is incorrect."),
    )
    dmarc_status = models.TextField(
        _("DMARC status"),
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("DMARC record check result on the root domain."),
    )
    dmarc_error = models.TextField(
        _("DMARC error"),
        blank=True,
        help_text=_("Failure detail if the DMARC record is incorrect."),
    )
    mta_sts_status = models.TextField(
        _("MTA-STS status"),
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("MTA-STS record check result on the root domain."),
    )
    mta_sts_error = models.TextField(
        _("MTA-STS error"),
        blank=True,
        help_text=_("Failure detail if the MTA-STS record is incorrect."),
    )
    tls_rpt_status = models.TextField(
        _("TLS-RPT status"),
        choices=Status,
        default=Status.UNCHECKED,
        help_text=_("TLS-RPT record check result on the root domain."),
    )
    tls_rpt_error = models.TextField(
        _("TLS-RPT error"),
        blank=True,
        help_text=_("Failure detail if the TLS-RPT record is incorrect."),
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
            "RSA-1024 DKIM signing key. For compatibility with older verifiers."
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
        return f"{self.name} (managed)" if self.is_managed else self.name

    class Meta(TimeStamped.Meta):
        indexes = [
            models.Index(Lower("name"), name="domain_name_lower_idx"),
        ]

    objects = models.Manager.from_queryset(DomainQuerySet)()

    def get_absolute_url(self):
        return reverse(
            "domains:domain-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    def save(self, *args, **kwargs):
        self.name = canonicalize_domain_name(self.name)
        self.clean()
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and self.dkim_key_rsa2048_id is None:
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

    is_managed = models.BooleanField(
        _("managed"),
        default=False,
        help_text=_("Whether relay manages this domain's DNS automatically."),
    )

    def clean(self):
        name = canonicalize_domain_name(self.name)
        self.name = name
        if not self.is_managed:
            root = canonicalize_domain_name(settings.RELAY_MANAGED_SENDER_DOMAIN)
            if name == root or name.endswith(f".{root}"):
                raise ValidationError(
                    _(
                        "Cannot add a subdomain of %(base)s. relay manages these automatically."
                    )
                    % {"base": root}
                )

        if self.org_id:
            parts = name.split(".")
            ancestors = [".".join(parts[index:]) for index in range(len(parts))]
            overlapping_domains = Domain.objects.exclude(org_id=self.org_id).filter(
                reduce(or_, (models.Q(name__iexact=value) for value in ancestors))
                | models.Q(name__iendswith=f".{name}")
            )
            platform_name = canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN)
            # A conflict is skipped exactly when one of the two compared
            # rows is the platform domain, which by design is the ancestor
            # of every managed sender domain.
            if name == platform_name:
                overlapping_domains = Domain.objects.none()
            else:
                overlapping_domains = overlapping_domains.exclude(
                    name__iexact=platform_name
                )
            if self.pk:
                overlapping_domains = overlapping_domains.exclude(pk=self.pk)
            if overlapping_domains.exists():
                raise ValidationError(
                    {
                        "name": _(
                            "Domain overlaps with a domain owned by another organization."
                        )
                    }
                )

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
        """Return the subdomain used as the SMTP envelope and DKIM sender."""
        return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{self.name}"

    @property
    def dmarc_record_name(self):
        return f"_dmarc.{self.name}"

    def dkim_cname_for_selector(self, selector: str) -> tuple[str, str]:
        base = self.sender_domain
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
        """Return the DMARC record for the root domain, with rua/ruf pointing to the sender subdomain."""
        return (
            f"v=DMARC1; p=quarantine; sp=quarantine; adkim=r; aspf=r;"
            f" rua=mailto:{self.dmarc_reporting_address};"
            f" ruf=mailto:{self.dmarc_ruf_reporting_address};"
        )

    @property
    def tls_rpt_record(self):
        """Return the TLS-RPT record with rua pointing to the sender subdomain."""
        return f"v=TLSRPTv1;rua=mailto:{self.tls_reporting_address}"

    @property
    def sender_dmarc_record(self):
        """Return the DMARC record served at _dmarc.{sender_subdomain} for external reporting authorization."""
        return "v=DMARC1; p=quarantine"

    @property
    def mta_sts_record(self):
        """Return the MTA-STS DNS record for _mta-sts.{domain}."""
        return f"v=STSv1; id={settings.RELAY_MTA_STS_POLICY_ID}"
