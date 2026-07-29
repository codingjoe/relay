import uuid

from django.db import connection, models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from mx.models import IncomingMessage


def adopt_incoming_message(cls, message, **extra):
    """Promote an existing IncomingMessage to a report type via multi-table inheritance."""
    instance = cls(**extra)
    parent_ptr = instance._meta.parents[IncomingMessage]
    setattr(instance, parent_ptr.attname, message.pk)
    for field in message._meta.concrete_fields:
        setattr(instance, field.attname, getattr(message, field.attname))
    local_fields = instance._meta.local_fields
    columns = [f.column for f in local_fields]
    values = [
        f.get_db_prep_save(f.value_from_object(instance), connection)
        for f in local_fields
    ]
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {instance._meta.db_table}"
            f" ({', '.join(columns)}) VALUES ({', '.join(['%s'] * len(columns))})",
            values,
        )
    return instance


class DmarcReport(IncomingMessage):
    """Aggregate DMARC report received from a reporting organization."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        PARSED = "parsed", _("parsed")
        FAILED = "failed", _("failed")

    class Disposition(models.TextChoices):
        NONE = "none", _("none")
        QUARANTINE = "quarantine", _("quarantine")
        REJECT = "reject", _("reject")

    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dmarc_reports",
        help_text=_("Monitored domain."),
    )
    reporting_org = models.TextField(
        _("reporting organization"),
        blank=True,
        help_text=_("Organization that generated the report (from XML metadata)."),
    )
    reporting_email = models.EmailField(
        _("reporting email"),
        blank=True,
        help_text=_("Contact email from the report metadata."),
    )
    report_id = models.TextField(
        _("report ID"),
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
    report_status = models.TextField(
        _("report status"),
        choices=Status,
        default=Status.RECEIVED,
        help_text=_("Report processing lifecycle state."),
    )
    error = models.TextField(
        _("error"),
        blank=True,
        help_text=_("Parse error detail if processing failed."),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "report_id"],
                name="unique_dmarc_report",
            ),
        ]
        indexes = [
            models.Index(fields=["report_status"]),
            models.Index(fields=["begin_at"]),
        ]

    def __str__(self):
        return f"{self.reporting_org} → {self.domain or '?'} ({self.report_id})"

    def get_absolute_url(self):
        return reverse(
            "dmarc:report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    @classmethod
    def adopt(cls, message, **extra):
        return adopt_incoming_message(cls, message, **extra)

    @classmethod
    def parse_from_email(cls, raw_bytes):
        """Return a DmarcReport instance and DmarcRecord list parsed from a raw email.

        Raises ``ValueError`` if no XML attachment is found.
        """
        from .parser import extract_attachment, parse_dmarc_xml

        data = extract_attachment(raw_bytes)
        if data is None:
            raise ValueError("No attachment found in DMARC report email.")
        parsed = parse_dmarc_xml(data)
        meta = parsed["metadata"]
        report = cls(
            reporting_org=meta["reporting_org"],
            reporting_email=meta["reporting_email"],
            report_id=meta["report_id"],
            begin_at=meta["begin_at"],
            end_at=meta["end_at"],
            report_status=cls.Status.PARSED,
        )
        records = [
            DmarcRecord(report=report, **record_data)
            for record_data in parsed["records"]
        ]
        return report, records


class DmarcRecord(TimeStamped):
    """Source-IP record within a DMARC aggregate report."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

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
    disposition = models.TextField(
        _("disposition"),
        choices=DmarcReport.Disposition,
        help_text=_("DMARC policy outcome for this source."),
    )
    dkim_alignment = models.TextField(
        _("DKIM alignment"),
        choices=Alignment,
        help_text=_("DKIM alignment result."),
    )
    spf_alignment = models.TextField(
        _("SPF alignment"),
        choices=Alignment,
        help_text=_("SPF alignment result."),
    )
    header_from = models.TextField(
        _("header from"),
        blank=True,
        help_text=_("From header domain."),
    )
    envelope_from = models.TextField(
        _("envelope from"),
        blank=True,
        help_text=_("Envelope sender domain (MAIL FROM)."),
    )
    dkim_domain = models.TextField(
        _("DKIM domain"),
        blank=True,
        help_text=_("DKIM signing domain."),
    )
    dkim_result = models.TextField(
        _("DKIM result"),
        choices=AuthResult,
        blank=True,
        help_text=_("DKIM authentication result."),
    )
    spf_domain = models.TextField(
        _("SPF domain"),
        blank=True,
        help_text=_("SPF checked domain."),
    )
    spf_result = models.TextField(
        _("SPF result"),
        choices=AuthResult,
        blank=True,
        help_text=_("SPF authentication result."),
    )

    class Meta:
        indexes = [
            models.Index(fields=["report", "source_ip_address"]),
        ]

    def __str__(self):
        return f"{self.source_ip_address} ×{self.count} ({self.disposition})"


class DmarcFailureReport(IncomingMessage):
    """DMARC forensic (RUF) report received from a reporting organization."""

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

    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dmarc_failure_reports",
        help_text=_("Monitored domain."),
    )
    reporting_org = models.TextField(
        _("reporting organization"),
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
    delivery_result = models.TextField(
        _("delivery result"),
        choices=DeliveryResult,
        default=DeliveryResult.OTHER,
        help_text=_("What the reporting MTA did with the message."),
    )
    original_headers = models.TextField(
        _("original headers"),
        blank=True,
        help_text=_("Headers of the original message from the report."),
    )
    report_status = models.TextField(
        _("report status"),
        choices=Status,
        default=Status.RECEIVED,
        help_text=_("Report processing lifecycle state."),
    )
    error = models.TextField(
        _("error"),
        blank=True,
        help_text=_("Parse error detail if processing failed."),
    )

    class Meta:
        indexes = [
            models.Index(fields=["report_status"]),
            models.Index(fields=["arrival_at"]),
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

    @classmethod
    def adopt(cls, message, **extra):
        return adopt_incoming_message(cls, message, **extra)

    @classmethod
    def parse_from_email(cls, raw_bytes):
        """Return a DmarcFailureReport instance parsed from a raw ARF email.

        Raises ``ValueError`` if no ARF feedback-report content is found.
        """
        from .parser import parse_arf

        parsed = parse_arf(raw_bytes)
        return cls(
            reporting_org=parsed["reporting_org"],
            reporting_email=parsed["reporting_email"],
            source_ip_address=parsed["source_ip_address"] or None,
            arrival_at=parsed["arrival_at"],
            original_mail_from=parsed["original_mail_from"],
            original_rcpt_to=parsed["original_rcpt_to"],
            authentication_results=parsed["authentication_results"],
            delivery_result=parsed["delivery_result"],
            original_headers=parsed["original_headers"],
            report_status=cls.Status.PARSED,
        )
