import uuid

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import OrganizationOwned
from services.email.message.models import Message

from .parser import parse_fbl


class FblReport(OrganizationOwned):
    """
    Feedback Loop (FBL) complaint report.

    FBL reports use the ARF (Abuse Reporting Format, RFC 5965) MIME structure.
    They are similar to DMARC RUF reports but carry complaint feedback
    (for example, a user clicked "mark as spam") rather than authentication
    failure details.

    Reports are records only. Relay does not send reports anywhere. A
    provider report is two messages, the ARF email the provider sent and the
    message Relay sent that was complained about, so it references both.
    """

    id = models.UUIDField(
        _("ID"),
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

    message = models.ForeignKey(
        "message.Message",
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_(
            "ARF email the provider sent, or the message Relay flagged. Not "
            "the message complained about, see complained_message."
        ),
    )
    complained_message = models.ForeignKey(
        "message.Message",
        on_delete=models.CASCADE,
        related_name="+",
        help_text=_(
            "Message the recipient complained about, not the report email. "
            "Repeated reports about one message count once."
        ),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.PROTECT,
        related_name="+",
        help_text=_("Domain the report is about."),
    )

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
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["arrival_at"], name="reputation__arrival_8495bd_idx"),
            models.Index(
                fields=["feedback_type"], name="reputation__feedbac_bddb85_idx"
            ),
        ]

    @property
    def status_badge_variant(self) -> str:
        return "destructive"

    def __str__(self):
        return f"{self.reporting_org} → {self.domain.name} ({self.original_mail_from})"

    def __repr__(self):
        return f"<FblReport {self.pk}>"

    def get_absolute_url(self):
        return reverse(
            "monitoring:fbl-report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    @classmethod
    def parse_from_email(cls, raw_bytes):
        """
        Return an unsaved FblReport.

        Raises `ValueError` if no ARF feedback-report content is found.
        """
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
    def create_for_incoming(cls, message, complained_message):
        """Store an FBL report email against the message it complains about."""
        with transaction.atomic():
            report = cls.objects.create(
                source=cls.Source.PROVIDER,
                org=complained_message.org,
                domain=complained_message.domain,
                message=message,
                complained_message=complained_message,
            )
            # Attached parent messages carry child statuses; save() would
            # reject them, so move the email with a queryset update.
            Message.objects.filter(pk=message.pk).update(
                org=complained_message.org,
                domain=complained_message.domain,
                modified_at=timezone.now(),
            )
        return report

    @classmethod
    def create_for_spam(cls, message):
        """
        Store a relay-generated FBL report for a spam-flagged message.

        Covers MSA-held outgoing messages and MTA-quarantined incoming
        messages. Relay-generated reports are for visibility only and do
        not count as complaints.
        """
        return cls.objects.create(
            source=cls.Source.RELAY,
            org=message.org,
            domain=message.domain,
            message=message,
            complained_message=message,
            feedback_type=cls.FeedbackType.ABUSE,
            user_agent="relay",
            version="1",
            reporting_org="relay",
            reporting_email=settings.FBL_ADDRESS,
            original_mail_from=message.mail_from,
            original_rcpt_to=message.rcpt_to.split(",")[0],
            original_message_id=message.message_id,
        )
