"""DMARC aggregate and TLS-RPT report models."""

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


class DmarcReport(TimeStamped):
    """An aggregate DMARC report received from a reporting organization."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        PARSED = "parsed", _("parsed")
        FAILED = "failed", _("failed")

    class Disposition(models.TextChoices):
        NONE = "none", _("none")
        QUARANTINE = "quarantine", _("quarantine")
        REJECT = "reject", _("reject")

    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="dmarc_reports",
        help_text=_("Owning organization."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dmarc_reports",
        help_text=_("Monitored domain."),
    )
    reporting_org = models.CharField(
        _("reporting organization"),
        max_length=255,
        blank=True,
        help_text=_("Organization that generated the report (from XML metadata)."),
    )
    reporting_email = models.EmailField(
        _("reporting email"),
        blank=True,
        help_text=_("Contact email from the report metadata."),
    )
    report_id = models.CharField(
        _("report ID"),
        max_length=255,
        help_text=_("Unique report identifier from the reporting organization."),
    )
    begin_at = models.DateTimeField(
        _("begin at"),
        null=True,
        blank=True,
        help_text=_("Start of the report period."),
    )
    end_at = models.DateTimeField(
        _("end at"),
        null=True,
        blank=True,
        help_text=_("End of the report period."),
    )
    raw_email = models.FileField(
        _("raw email"),
        upload_to="dmarc_reports/",
        help_text=_("Raw report email with XML attachment."),
    )
    status = models.CharField(
        _("status"),
        max_length=8,
        choices=Status,
        default=Status.RECEIVED,
        help_text=_("Report processing lifecycle state."),
    )
    error = models.TextField(
        _("error"),
        blank=True,
        help_text=_("Parse error detail if processing failed."),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "report_id"],
                name="unique_dmarc_report",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "status"]),
            models.Index(fields=["org", "begin_at"]),
        ]

    def __str__(self):
        return f"{self.reporting_org} → {self.domain or '?'} ({self.report_id})"

    def get_absolute_url(self):
        return reverse(
            "dmarc:report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )


class DmarcRecord(TimeStamped):
    """A single source-IP record within a DMARC aggregate report."""

    class Alignment(models.TextChoices):
        PASS = "pass", _("pass")
        FAIL = "fail", _("fail")

    class AuthResult(models.TextChoices):
        PASS = "pass", _("pass")
        FAIL = "fail", _("fail")
        NEUTRAL = "neutral", _("neutral")
        NONE = "none", _("none")
        PERMERROR = "permerror", _("permerror")
        TEMPERROR = "temperror", _("temperror")

    report = models.ForeignKey(
        DmarcReport,
        on_delete=models.CASCADE,
        related_name="records",
    )
    source_ip_address = models.GenericIPAddressField(
        _("source IP address"),
        help_text=_("Sending IP address."),
    )
    count = models.PositiveIntegerField(
        _("count"),
        default=0,
        help_text=_("Number of messages from this source IP."),
    )
    disposition = models.CharField(
        _("disposition"),
        max_length=10,
        choices=DmarcReport.Disposition,
        help_text=_("DMARC policy outcome for this source."),
    )
    dkim_alignment = models.CharField(
        _("DKIM alignment"),
        max_length=4,
        choices=Alignment,
        help_text=_("DKIM alignment result."),
    )
    spf_alignment = models.CharField(
        _("SPF alignment"),
        max_length=4,
        choices=Alignment,
        help_text=_("SPF alignment result."),
    )
    header_from = models.CharField(
        _("header from"),
        max_length=255,
        blank=True,
        help_text=_("From header domain."),
    )
    envelope_from = models.CharField(
        _("envelope from"),
        max_length=255,
        blank=True,
        help_text=_("Envelope sender domain (MAIL FROM)."),
    )
    dkim_domain = models.CharField(
        _("DKIM domain"),
        max_length=255,
        blank=True,
        help_text=_("DKIM signing domain."),
    )
    dkim_result = models.CharField(
        _("DKIM result"),
        max_length=9,
        choices=AuthResult,
        blank=True,
        help_text=_("DKIM authentication result."),
    )
    spf_domain = models.CharField(
        _("SPF domain"),
        max_length=255,
        blank=True,
        help_text=_("SPF checked domain."),
    )
    spf_result = models.CharField(
        _("SPF result"),
        max_length=9,
        choices=AuthResult,
        blank=True,
        help_text=_("SPF authentication result."),
    )

    class Meta(TimeStamped.Meta):
        indexes = [
            models.Index(fields=["report", "source_ip_address"]),
        ]

    def __str__(self):
        return f"{self.source_ip_address} ×{self.count} ({self.disposition})"


class TlsReport(TimeStamped):
    """A TLS-RPT report received from a sending organization."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        PARSED = "parsed", _("parsed")
        FAILED = "failed", _("failed")

    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="tls_reports",
        help_text=_("Owning organization."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tls_reports",
        help_text=_("Domain the report covers."),
    )
    reporting_org = models.CharField(
        _("reporting organization"),
        max_length=255,
        blank=True,
        help_text=_("Organization that generated the report."),
    )
    reporting_email = models.EmailField(
        _("reporting email"),
        blank=True,
        help_text=_("Contact email from the report metadata."),
    )
    report_id = models.CharField(
        _("report ID"),
        max_length=255,
        help_text=_("Unique report identifier."),
    )
    begin_at = models.DateTimeField(
        _("begin at"),
        null=True,
        blank=True,
        help_text=_("Start of the report period."),
    )
    end_at = models.DateTimeField(
        _("end at"),
        null=True,
        blank=True,
        help_text=_("End of the report period."),
    )
    raw_email = models.FileField(
        _("raw email"),
        upload_to="tls_reports/",
        help_text=_("Raw report email with JSON attachment."),
    )
    status = models.CharField(
        _("status"),
        max_length=8,
        choices=Status,
        default=Status.RECEIVED,
        help_text=_("Report processing lifecycle state."),
    )
    error = models.TextField(
        _("error"),
        blank=True,
        help_text=_("Parse error detail if processing failed."),
    )
    successful_session_count = models.PositiveIntegerField(
        _("successful session count"),
        default=0,
        help_text=_("Total successful TLS sessions."),
    )
    failed_session_count = models.PositiveIntegerField(
        _("failed session count"),
        default=0,
        help_text=_("Total failed TLS sessions."),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "report_id"],
                name="unique_tls_report",
            ),
        ]
        indexes = [
            models.Index(fields=["org", "status"]),
            models.Index(fields=["org", "begin_at"]),
        ]

    def __str__(self):
        return f"{self.reporting_org} → {self.domain or '?'} ({self.report_id})"

    def get_absolute_url(self):
        return reverse(
            "dmarc:tls-report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )


class TlsFailure(TimeStamped):
    """A single TLS failure record within a TLS-RPT report."""

    class PolicyType(models.TextChoices):
        STS = "sts", _("STS")
        TLSA = "tlsa", _("TLSA")

    class ResultType(models.TextChoices):
        STARTTLS_NOT_SUPPORTED = "starttls-not-supported", _("STARTTLS not supported")
        CERTIFICATE_EXPIRED = "certificate-expired", _("certificate expired")
        CERTIFICATE_NOT_TRUSTED = (
            "certificate-not-trusted",
            _("certificate not trusted"),
        )
        CERTIFICATE_NAME_MISMATCH = (
            "certificate-name-mismatch",
            _("certificate name mismatch"),
        )
        TLS_VERSION_INVALID = "tls-version-invalid", _("TLS version invalid")
        TLSA_INVALID = "tlsa-invalid", _("TLSA invalid")
        DANE_REQUIRED = "dane-required", _("DANE required")
        STS_POLICY_INVALID = "sts-policy-invalid", _("STS policy invalid")
        STS_WEBPKI_INVALID = "sts-webpki-invalid", _("STS WebPKI invalid")
        OTHER = "other", _("other")

    report = models.ForeignKey(
        TlsReport,
        on_delete=models.CASCADE,
        related_name="failures",
    )
    policy_type = models.CharField(
        _("policy type"),
        max_length=4,
        choices=PolicyType,
        help_text=_("Policy that was applied."),
    )
    policy_domain = models.CharField(
        _("policy domain"),
        max_length=255,
        blank=True,
        help_text=_("Domain the policy applies to."),
    )
    result_type = models.CharField(
        _("result type"),
        max_length=28,
        choices=ResultType,
        help_text=_("TLS failure type."),
    )
    sending_mta_ip_address = models.GenericIPAddressField(
        _("sending MTA IP address"),
        help_text=_("IP address of the sending MTA."),
    )
    receiving_mx_hostname = models.CharField(
        _("receiving MX hostname"),
        max_length=255,
        blank=True,
        help_text=_("Hostname of the receiving MX."),
    )
    receiving_mx_ip_address = models.GenericIPAddressField(
        _("receiving MX IP address"),
        null=True,
        blank=True,
        help_text=_("IP address of the receiving MX."),
    )
    count = models.PositiveIntegerField(
        _("count"),
        default=0,
        help_text=_("Number of failed sessions with this configuration."),
    )
    additional_info = models.TextField(
        _("additional info"),
        blank=True,
        help_text=_("Extra failure details from the report."),
    )

    class Meta(TimeStamped.Meta):
        indexes = [
            models.Index(fields=["report", "result_type"]),
        ]

    def __str__(self):
        return f"{self.get_result_type_display()} ×{self.count} ({self.receiving_mx_hostname})"
