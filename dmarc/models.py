"""DMARC aggregate report, forensic report, and evaluation models."""

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
    incoming_message = models.OneToOneField(
        "mx.IncomingMessage",
        on_delete=models.CASCADE,
        related_name="dmarc_report",
        help_text=_("Incoming email that delivered this report."),
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


class DmarcFailureReport(TimeStamped):
    """A DMARC forensic (RUF) report received from a reporting organization."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        PARSED = "parsed", _("parsed")
        FAILED = "failed", _("failed")

    class DeliveryResult(models.TextChoices):
        DELIVERED = "delivered", _("delivered")
        SPAM = "spam", _("spam")
        POLICY = "policy", _("policy")
        REJECTED = "rejected", _("rejected")
        OTHER = "other", _("other")

    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="dmarc_failure_reports",
        help_text=_("Owning organization."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dmarc_failure_reports",
        help_text=_("Monitored domain."),
    )
    incoming_message = models.OneToOneField(
        "mx.IncomingMessage",
        on_delete=models.CASCADE,
        related_name="dmarc_failure_report",
        help_text=_("Incoming email that delivered this report."),
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
    source_ip_address = models.GenericIPAddressField(
        _("source IP address"),
        null=True,
        blank=True,
        help_text=_("Sending IP address."),
    )
    arrival_at = models.DateTimeField(
        _("arrival at"),
        null=True,
        blank=True,
        help_text=_("When the original message was received."),
    )
    original_mail_from = models.EmailField(
        _("original mail from"),
        blank=True,
        help_text=_("Envelope sender of the original message."),
    )
    original_rcpt_to = models.EmailField(
        _("original rcpt to"),
        blank=True,
        help_text=_("Envelope recipient of the original message."),
    )
    authentication_results = models.TextField(
        _("authentication results"),
        blank=True,
        help_text=_("SPF and DKIM authentication results from the report."),
    )
    delivery_result = models.CharField(
        _("delivery result"),
        max_length=9,
        choices=DeliveryResult,
        default=DeliveryResult.OTHER,
        help_text=_("What the reporting MTA did with the message."),
    )
    original_headers = models.TextField(
        _("original headers"),
        blank=True,
        help_text=_("Headers of the original message from the report."),
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
        indexes = [
            models.Index(fields=["org", "status"]),
            models.Index(fields=["org", "arrival_at"]),
        ]

    def __str__(self):
        return (
            f"{self.reporting_org} → {self.domain or '?'} ({self.original_mail_from})"
        )

    def get_absolute_url(self):
        return reverse(
            "dmarc:failure-report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )


class DmarcEvaluation(TimeStamped):
    """DMARC evaluation result for a single incoming message.

    Tracks SPF/DKIM authentication and DMARC policy evaluation so that
    aggregate (RUA) and forensic (RUF) reports can be generated for
    outbound delivery.
    """

    class Disposition(models.TextChoices):
        NONE = "none", _("none")
        QUARANTINE = "quarantine", _("quarantine")
        REJECT = "reject", _("reject")

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

    incoming_message = models.OneToOneField(
        "mx.IncomingMessage",
        on_delete=models.CASCADE,
        related_name="dmarc_evaluation",
        help_text=_("Incoming message that was evaluated."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dmarc_evaluations",
        help_text=_("Domain being evaluated (header-from domain)."),
    )
    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="dmarc_evaluations",
        help_text=_("Owning organization."),
    )
    source_ip_address = models.GenericIPAddressField(
        _("source IP address"),
        null=True,
        blank=True,
        help_text=_("Sending IP address."),
    )
    disposition = models.CharField(
        _("disposition"),
        max_length=10,
        choices=Disposition,
        default=Disposition.NONE,
        help_text=_("DMARC policy outcome."),
    )
    dkim_alignment = models.CharField(
        _("DKIM alignment"),
        max_length=4,
        choices=Alignment,
        default=Alignment.FAIL,
        help_text=_("DKIM alignment result."),
    )
    spf_alignment = models.CharField(
        _("SPF alignment"),
        max_length=4,
        choices=Alignment,
        default=Alignment.FAIL,
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
        default=AuthResult.NONE,
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
        default=AuthResult.NONE,
        help_text=_("SPF authentication result."),
    )
    included_in_report = models.BooleanField(
        _("included in report"),
        default=False,
        help_text=_("Whether this evaluation has been included in a sent report."),
    )

    class Meta(TimeStamped.Meta):
        indexes = [
            models.Index(fields=["domain", "included_in_report"]),
            models.Index(fields=["org", "disposition"]),
        ]

    def __str__(self):
        return f"{self.source_ip_address} → {self.header_from} ({self.disposition})"


class OutgoingDmarcReport(TimeStamped):
    """A DMARC aggregate (RUA) report generated and sent by Relay."""

    class Status(models.TextChoices):
        GENERATING = "generating", _("generating")
        SENT = "sent", _("sent")
        FAILED = "failed", _("failed")

    class ReportType(models.TextChoices):
        RUA = "rua", _("RUA")
        RUF = "ruf", _("RUF")

    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="outgoing_dmarc_reports",
        help_text=_("Owning organization."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_dmarc_reports",
        help_text=_("Domain the report covers."),
    )
    report_type = models.CharField(
        _("report type"),
        max_length=3,
        choices=ReportType,
        default=ReportType.RUA,
        help_text=_("RUA (aggregate) or RUF (forensic)."),
    )
    recipient = models.EmailField(
        _("recipient"),
        help_text=_("Email address the report was sent to."),
    )
    begin_at = models.DateTimeField(
        _("begin at"),
        help_text=_("Start of the report period."),
    )
    end_at = models.DateTimeField(
        _("end at"),
        help_text=_("End of the report period."),
    )
    record_count = models.PositiveIntegerField(
        _("record count"),
        default=0,
        help_text=_("Number of records included in the report."),
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status,
        default=Status.GENERATING,
        help_text=_("Report sending lifecycle state."),
    )
    error = models.TextField(
        _("error"),
        blank=True,
        help_text=_("Error detail if sending failed."),
    )

    class Meta(TimeStamped.Meta):
        indexes = [
            models.Index(fields=["org", "status"]),
            models.Index(fields=["domain", "report_type"]),
        ]

    def __str__(self):
        return f"{self.domain} → {self.recipient} ({self.report_type})"
