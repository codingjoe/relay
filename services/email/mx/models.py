import base64
import uuid
from fnmatch import fnmatch

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.email_utils import iter_attachments
from abstract.models import TimeStamped
from accounts.models import OrganizationOwned
from domains.models import Domain
from kms.models import SigningKey
from services.email.message.models import Message

from .serializers import TlsReportSerializer


class IncomingMessage(Message):
    """Capture inbound mail from the MX server and track webhook dispatch."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        WEBHOOK_SENT = "webhook_sent", _("webhook sent")
        WEBHOOK_FAILED = "webhook_failed", _("webhook failed")
        DROPPED = "dropped", _("dropped")

    receiving_domain = models.TextField(
        _("receiving domain"),
        blank=True,
        help_text=_("Domain part of the recipient address, for example app.acme.com."),
    )
    status = models.TextField(
        _("status"),
        choices=Status,
        default=Status.RECEIVED,
        help_text=_("Ingress and webhook delivery lifecycle state."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.content_type_id:
            self.content_type = ContentType.objects.get_for_model(type(self))
        super().save(*args, **kwargs)

    @property
    def status_display(self) -> str:
        return self.get_status_display()

    @property
    def domain_name(self) -> str:
        return self.receiving_domain

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    def get_absolute_url(self):
        return reverse(
            "mx:message-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.id},
        )


class Webhook(OrganizationOwned):
    """Receive webhook deliveries for matching recipient addresses at an HTTPS endpoint."""

    class MxStatus(models.TextChoices):
        OK = "ok", _("ok")
        ERROR = "error", _("error")
        UNCHECKED = "unchecked", _("unchecked")

    url = models.URLField(
        _("URL"),
        validators=[
            RegexValidator(
                r"^https://",
                _("Webhook URL must use HTTPS."),
            ),
        ],
        help_text=_("HTTPS endpoint to receive incoming-mail webhook deliveries."),
    )
    name = models.TextField(
        _("name"),
        blank=True,
        help_text=_("Human-readable label."),
    )
    address_pattern = models.TextField(
        _("address pattern"),
        help_text=_(
            "Glob pattern for recipient addresses, for example *@app.acme.com "
            "or support@acme.com."
        ),
    )
    signing_key = models.ForeignKey(
        SigningKey,
        on_delete=models.PROTECT,
        related_name="webhooks",
        help_text=_("Ed25519 keypair used to sign webhook payloads."),
    )
    mx_status = models.TextField(
        _("MX status"),
        choices=MxStatus,
        default=MxStatus.UNCHECKED,
        help_text=_("MX record verification result for the receiving domain."),
    )
    mx_error = models.TextField(
        _("MX error"),
        blank=True,
        help_text=_("Failure detail if the MX record is incorrect."),
    )
    mx_checked_at = models.DateTimeField(
        _("MX checked at"),
        null=True,
        blank=True,
        help_text=_("Last MX check timestamp."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Inactive webhooks receive no deliveries."),
    )
    last_used_at = models.DateTimeField(
        _("last used"),
        null=True,
        blank=True,
        help_text=_("Last successful webhook delivery."),
    )

    def __str__(self):
        return f"{self.org} / {self.name or self.url}"

    @property
    def receiving_domain_name(self) -> str:
        if "@" in self.address_pattern:
            return self.address_pattern.split("@", 1)[1]
        return self.address_pattern

    @property
    def is_free_domain(self) -> bool:
        return (
            self.receiving_domain_name.lower()
            == settings.RELAY_FREE_SENDER_DOMAIN.lower()
        )

    @property
    def mx_target(self) -> str:
        receiving = self.receiving_domain_name.lower()
        try:
            return Domain.objects.root_for(receiving).sender_domain
        except Domain.DoesNotExist:
            return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{receiving}"

    @property
    def mx_record(self) -> str:
        if self.is_free_domain:
            return ""
        return f"MX {self.receiving_domain_name} → {self.mx_target}"

    def matches(self, rcpt_to) -> bool:
        return fnmatch(rcpt_to.lower(), self.address_pattern.lower())

    @property
    def public_key_serialized(self) -> str:
        return f"whpk_{base64.b64encode(self.signing_key.public_bytes_raw()).decode()}"

    def sign(self, msg_id: str, timestamp: int, payload: bytes) -> str:
        signed_content = f"{msg_id}.{timestamp}.".encode() + payload
        return f"v1a,{base64.b64encode(self.signing_key.sign(signed_content)).decode()}"


class WebhookDelivery(TimeStamped):
    """Track one webhook POST attempt and its outcome."""

    class Status(models.TextChoices):
        SENT = "sent", _("sent")
        FAILED = "failed", _("failed")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    message = models.ForeignKey(
        IncomingMessage,
        on_delete=models.CASCADE,
        related_name="webhook_deliveries",
        null=True,
        blank=True,
        help_text=_("Associated incoming message, or null for a test delivery."),
    )
    webhook = models.ForeignKey(
        Webhook,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    is_test = models.BooleanField(
        _("test"),
        default=False,
        help_text=_("Whether this was a test delivery."),
    )
    status = models.TextField(
        _("status"),
        choices=Status,
        help_text=_("Outcome of this webhook delivery attempt."),
    )
    response_code = models.PositiveIntegerField(
        _("response code"),
        null=True,
        blank=True,
        help_text=_("HTTP status code returned by the webhook endpoint."),
    )
    response_body = models.TextField(
        _("response body"),
        blank=True,
        help_text=_("Truncated response body from the webhook endpoint."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]

    @property
    def status_badge_variant(self) -> str:
        match self.status:
            case self.Status.SENT:
                return "primary"
            case self.Status.FAILED:
                return "destructive"
            case _:
                return "outline"

    def __str__(self):
        return f"{self.webhook} ({self.status})"


class TlsReport(IncomingMessage):
    """Receive TLS-RPT reports from sending organizations."""

    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tls_reports",
        help_text=_("Domain the report covers."),
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
    report_id = models.TextField(
        _("report ID"),
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

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["domain", "report_id"],
                name="unique_tls_report",
            ),
        ]
        indexes = [
            models.Index(fields=["begin_at"]),
        ]

    def __str__(self):
        return f"{self.reporting_org} → {self.domain or '?'} ({self.report_id})"

    def get_absolute_url(self):
        return reverse(
            "mx:tls-report-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    @classmethod
    def parse_from_email(cls, raw_bytes):
        """Return a TlsReport instance and TlsFailure list parsed from a raw email.

        Raises `ValueError` if no JSON attachment is found.
        """
        data = next(iter_attachments(raw_bytes), None)
        if data is None:
            raise ValueError("No attachment found in TLS-RPT report email.")
        meta, policies = TlsReportSerializer.parse_json(data)
        report = cls(
            reporting_org=meta["reporting_org"],
            reporting_email=meta["reporting_email"],
            report_id=meta["report_id"],
            begin_at=meta["begin_at"],
            end_at=meta["end_at"],
        )
        failures = []
        total_successful = 0
        total_failed = 0
        for policy in policies:
            total_successful += policy["successful_session_count"]
            total_failed += policy["failed_session_count"]
            for failure_data in policy["failures"]:
                failure_data["policy_type"] = policy["policy_type"]
                failure_data["policy_domain"] = policy["policy_domain"]
                failures.append(TlsFailure(report=report, **failure_data))
        report.successful_session_count = total_successful
        report.failed_session_count = total_failed
        return report, failures


class TlsFailure(TimeStamped):
    """TLS failure record within a TLS-RPT report."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )

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
    policy_type = models.TextField(
        _("policy type"),
        choices=PolicyType,
        help_text=_("Policy that was applied."),
    )
    policy_domain = models.TextField(
        _("policy domain"),
        blank=True,
        help_text=_("Domain the policy applies to."),
    )
    result_type = models.TextField(
        _("result type"),
        choices=ResultType,
        help_text=_("TLS failure type."),
    )
    sending_mta_ip_address = models.GenericIPAddressField(
        _("sending MTA IP address"),
        help_text=_("IP address of the sending MTA."),
    )
    receiving_mx_hostname = models.TextField(
        _("receiving MX hostname"),
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
