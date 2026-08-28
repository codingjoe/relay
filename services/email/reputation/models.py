from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from services.email.mta.models import IncomingMessage


class FblReport(IncomingMessage):
    """Feedback Loop (FBL) complaint report received from an email provider.

    FBL reports use the ARF (Abuse Reporting Format, RFC 5965) MIME structure.
    They are similar to DMARC RUF reports but carry complaint feedback
    (for example, a user clicked "mark as spam") rather than authentication
    failure details.
    """

    class FeedbackType(models.TextChoices):
        ABUSE = "abuse", _("abuse")
        FRAUD = "fraud", _("fraud")
        VIRUS = "virus", _("virus")
        NOT_SPAM = "not-spam", _("not-spam")
        OPT_OUT = "opt-out", _("opt-out")
        OTHER = "other", _("other")

    class Source(models.TextChoices):
        PROVIDER = "provider", _("provider")
        RELAY = "relay", _("relay")

    source = models.TextField(
        _("source"),
        choices=Source,
        default=Source.PROVIDER,
        help_text=_(
            "Provider reports were received from a mailbox provider and count "
            "as complaints. Relay-generated reports are records of spam Relay "
            "detected itself and are for visibility only."
        ),
    )
    feedback_type = models.TextField(
        _("feedback type"),
        choices=FeedbackType,
        default=FeedbackType.ABUSE,
        help_text=_("ARF feedback type indicating the nature of the complaint."),
    )
    user_agent = models.TextField(
        _("user agent"),
        blank=True,
        help_text=_("Reporting system that generated the FBL report."),
    )
    version = models.TextField(
        _("version"),
        blank=True,
        help_text=_("ARF version from the feedback report."),
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
        help_text=_("Original sending IP address."),
    )
    arrival_at = models.DateTimeField(
        _("arrival at"),
        null=True,
        blank=True,
        help_text=_(
            "When the original message was received by the reporting provider."
        ),
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
    original_message_id = models.TextField(
        _("original message ID"),
        blank=True,
        help_text=_("RFC 5322 Message-ID of the original message."),
    )
    authentication_results = models.TextField(
        _("authentication results"),
        blank=True,
        help_text=_("SPF and DKIM authentication results from the report."),
    )
    original_headers = models.TextField(
        _("original headers"),
        blank=True,
        help_text=_("Headers of the original message from the report."),
    )

    class Meta:
        indexes = [
            models.Index(fields=["arrival_at"]),
            models.Index(fields=["feedback_type"]),
        ]

    @property
    def status_badge_variant(self) -> str:
        return "destructive"

    def __str__(self):
        return (
            f"{self.reporting_org} → {self.domain or '?'} ({self.original_mail_from})"
        )

    def get_absolute_url(self):
        return reverse(
            "reputation:fbl-report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    @classmethod
    def parse_from_email(cls, raw_bytes):
        """Return an FblReport instance parsed from a raw ARF email.

        Raises `ValueError` if no ARF feedback-report content is found.
        """
        from .parser import parse_fbl

        parsed = parse_fbl(raw_bytes)
        return cls(
            feedback_type=parsed["feedback_type"],
            user_agent=parsed["user_agent"],
            version=parsed["version"],
            reporting_org=parsed["reporting_org"],
            reporting_email=parsed["reporting_email"],
            source_ip_address=parsed["source_ip_address"] or None,
            arrival_at=parsed["arrival_at"],
            original_mail_from=parsed["original_mail_from"],
            original_rcpt_to=parsed["original_rcpt_to"],
            original_message_id=parsed["original_message_id"],
            authentication_results=parsed["authentication_results"],
            original_headers=parsed["original_headers"],
        )

    @classmethod
    def create_for_spam(cls, message):
        """Create and store an FBL report for a message flagged as spam.

        Used for messages flagged as spam by Relay's own spam checks, both
        MSA-held outgoing messages and MTA-quarantined incoming messages.
        Relay-generated reports are for visibility only and do not count as
        complaints. Returns the created FblReport, or None if the message
        has no associated domain.
        """
        from django.core.files.base import ContentFile

        if message.domain_id is None:
            return None

        report = cls(
            source=cls.Source.RELAY,
            org=message.org,
            domain=message.domain,
            receiving_domain=getattr(message, "receiving_domain", ""),
            mail_from=message.mail_from,
            rcpt_to=message.rcpt_to,
            subject=message.subject,
            message_id=message.message_id,
            received_with_tls=message.received_with_tls,
            feedback_type=cls.FeedbackType.ABUSE,
            user_agent="relay",
            version="1",
            reporting_org="relay",
            reporting_email=f"{settings.RELAY_FBL_LOCAL_PART}@{settings.RELAY_PLATFORM_DOMAIN}",
            original_mail_from=message.mail_from,
            original_rcpt_to=message.rcpt_to.split(",")[0] if message.rcpt_to else "",
            original_message_id=message.message_id,
        )
        raw_bytes = message.raw_body.read() if message.raw_body else b""
        report.raw_body.save(f"{report.id}.eml", ContentFile(raw_bytes), save=False)
        report.save(force_insert=True)
        return report

    @classmethod
    def send_fbl_report(cls, message):
        """Send an ARF FBL report email to the sender domain's FBL address.

        Looks up the sender's domain and sends an ARF-formatted complaint
        report to its FBL reporting address. Does nothing if the sender
        domain is not registered or has no FBL address.
        """
        from django.core.mail import EmailMessage

        from domains.models import Domain

        sender_domain = (
            message.mail_from.split("@")[-1] if "@" in message.mail_from else ""
        )
        try:
            domain = Domain.objects.root_for(sender_domain, include_managed=True)
            address = domain.fbl_reporting_address
        except Domain.DoesNotExist, ValueError:
            address = ""

        match address:
            case "":
                return
            case _:
                raw_headers = ""
                if message.raw_body:
                    from email import message_from_bytes

                    parsed = message_from_bytes(message.raw_body.read())
                    raw_headers = "".join(f"{k}: {v}\r\n" for k, v in parsed.items())[
                        :2000
                    ]

                body = cls.build_arf_body(
                    source_ip="unknown",
                    arrival_date=message.created_at.isoformat(),
                    envelope_from=message.mail_from,
                    rcpt_to=message.rcpt_to,
                    delivery_result="spam",
                    original_headers=raw_headers,
                )
                email = EmailMessage(
                    subject=f"FBL report for {sender_domain}",
                    body=body,
                    from_email=f"{settings.RELAY_FBL_LOCAL_PART}@{settings.RELAY_PLATFORM_DOMAIN}",
                    to=[address],
                )
                email.send()
                return

    @staticmethod
    def build_arf_body(**fields):
        """Build an ARF (RFC 5965) multipart body for an FBL report."""
        lines = [
            "This is an email abuse report for an email message received from",
            f"IP {fields.get('source_ip', 'unknown')} on {fields.get('arrival_date', 'unknown')}.",
            "",
            "The message was flagged as spam.",
            "",
            "--boundary",
            "Content-Type: text/plain",
            "",
            "Feedback loop complaint report.",
            "",
            "--boundary",
            "Content-Type: message/feedback-report",
            "",
            "Feedback-Type: abuse",
            "User-Agent: relay",
            "Version: 1",
            f"Original-Mail-From: {fields.get('envelope_from', '')}",
            f"Original-Rcpt-To: {fields.get('rcpt_to', '')}",
            f"Arrival-Date: {fields.get('arrival_date', '')}",
            f"Source-IP: {fields.get('source_ip', '')}",
            f"Delivery-Result: {fields.get('delivery_result', 'spam')}",
            "",
            "--boundary",
            "Content-Type: text/rfc822-headers",
            "",
            fields.get("original_headers", ""),
            "",
            "--boundary--",
        ]
        return "\n".join(lines)
