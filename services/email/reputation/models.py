import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from accounts.models import OrganizationOwned

from .parser import parse_fbl


class FblReport(OrganizationOwned):
    """Feedback Loop (FBL) complaint report.

    FBL reports use the ARF (Abuse Reporting Format, RFC 5965) MIME structure.
    They are similar to DMARC RUF reports but carry complaint feedback
    (for example, a user clicked "mark as spam") rather than authentication
    failure details.

    Reports are records only. Relay does not send reports anywhere. The
    `message` foreign key references the report email received from a
    provider, or the message Relay flagged itself.
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
            "Referenced message: the ARF email received from a provider for "
            "provider reports, or the message Relay flagged for "
            "relay-generated reports."
        ),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        related_name="+",
        null=True,
        blank=True,
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
        """Return an unsaved instance built from a raw ARF message.

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
    def create_for_incoming(cls, message):
        """Store an FBL report email received at the FBL reporting address.

        The report is stored un-parsed and filled in later by the
        `parse_fbl_report` task.
        """
        return cls.objects.create(
            source=cls.Source.PROVIDER,
            org=message.org,
            domain=message.domain,
            message=message,
        )

    @classmethod
    def create_for_spam(cls, message):
        """Store a relay-generated FBL report for a message that Relay's own
        checks flagged.

        Covers MSA-held outgoing messages and MTA-quarantined incoming
        messages. Relay-generated reports are for visibility only and do
        not count as complaints. Returns `None` when the message has no
        associated domain.
        """
        if message.domain_id is None:
            return None

        return cls.objects.create(
            source=cls.Source.RELAY,
            org=message.org,
            domain=message.domain,
            message=message,
            feedback_type=cls.FeedbackType.ABUSE,
            user_agent="relay",
            version="1",
            reporting_org="relay",
            reporting_email=f"{settings.RELAY_FBL_LOCAL_PART}@{settings.RELAY_PLATFORM_DOMAIN}",
            original_mail_from=message.mail_from,
            original_rcpt_to=message.rcpt_to.split(",")[0],
            original_message_id=message.message_id,
        )
