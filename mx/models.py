"""MX ingress models — incoming messages, webhooks, and deliveries."""

import base64
import uuid
from datetime import timedelta
from fnmatch import fnmatch

import httpx
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.messages import MessageMixin
from abstract.models import TimeStamped
from accounts.models import OrganizationOwned
from domains.models import Domain
from kms.models import SigningKey


class IncomingMessage(MessageMixin, TimeStamped):
    """An email captured by the MX server, awaiting webhook dispatch."""

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        WEBHOOK_SENT = "webhook_sent", _("webhook sent")
        WEBHOOK_FAILED = "webhook_failed", _("webhook failed")
        DROPPED = "dropped", _("dropped")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="incoming_messages",
        help_text=_("Owning organization."),
    )
    receiving_domain = models.CharField(
        _("receiving domain"),
        max_length=255,
        blank=True,
        help_text=_("Domain part of the recipient address, e.g. app.acme.com."),
    )
    status = models.CharField(
        _("status"),
        max_length=14,
        choices=Status,
        default=Status.RECEIVED,
        help_text=_("Ingress and webhook delivery lifecycle state."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-received_at"]
        indexes = [
            models.Index(fields=["org", "status"]),
            models.Index(fields=["org", "received_at"]),
        ]

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    def get_absolute_url(self):
        return reverse(
            "mx:message-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.id},
        )


class Webhook(OrganizationOwned):
    """An HTTPS endpoint that receives webhook deliveries for matching addresses."""

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
    name = models.CharField(
        _("name"),
        max_length=255,
        blank=True,
        help_text=_("Human-readable label."),
    )
    address_pattern = models.CharField(
        _("address pattern"),
        max_length=255,
        help_text=_(
            "Glob pattern for recipient addresses, e.g. *@app.acme.com "
            "or support@acme.com."
        ),
    )
    signing_key = models.ForeignKey(
        SigningKey,
        on_delete=models.PROTECT,
        related_name="webhooks",
        help_text=_("Ed25519 keypair used to sign webhook payloads."),
    )
    mx_status = models.CharField(
        _("MX status"),
        max_length=9,
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
        if domain := Domain.objects.root_for(receiving).first():
            return domain.sender_domain
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
    """A record of one webhook POST attempt and its outcome."""

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
    status = models.CharField(
        _("status"),
        max_length=7,
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

    def __str__(self):
        return f"{self.webhook} ({self.status})"


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
    incoming_message = models.OneToOneField(
        IncomingMessage,
        on_delete=models.CASCADE,
        related_name="tls_report",
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
            "mx:tls-report-detail",
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


class MtaStsPolicy(TimeStamped):
    """Cached MTA-STS policy for a recipient domain."""

    class Status(models.TextChoices):
        LOADED = "loaded", _("loaded")
        FAILED = "failed", _("failed")
        NONE = "none", _("none")  # No MTA-STS policy published

    domain = models.CharField(
        _("domain"),
        max_length=255,
        unique=True,
        help_text=_("Recipient domain."),
    )
    policy_id = models.CharField(
        _("policy ID"),
        max_length=255,
        blank=True,
        help_text=_("STS policy ID from the well-known endpoint."),
    )
    status = models.CharField(
        _("status"),
        max_length=6,
        choices=Status,
        default=Status.NONE,
        help_text=_("Policy fetch result."),
    )
    mode = models.CharField(
        _("mode"),
        max_length=7,
        blank=True,
        help_text=_("STS mode: enforce, testing, or none."),
    )
    max_age_secs = models.PositiveIntegerField(
        _("max age (seconds)"),
        default=0,
        help_text=_("Policy max-age in seconds."),
    )
    mx_patterns = models.JSONField(
        _("MX patterns"),
        default=list,
        help_text=_("List of MX hostname patterns allowed by the policy."),
    )
    error = models.TextField(
        _("error"),
        blank=True,
        help_text=_("Fetch error detail if status is failed."),
    )
    checked_at = models.DateTimeField(
        _("checked at"),
        null=True,
        blank=True,
        help_text=_("Last successful policy fetch."),
    )

    def __str__(self):
        return f"{self.domain} ({self.status})"

    @classmethod
    def get_or_fetch(cls, domain):
        """Return a fresh policy for a domain, using the cache if still valid."""
        if policy := cls.objects.filter(domain=domain).first():
            max_age = timedelta(
                seconds=policy.max_age_secs or settings.RELAY_MTA_STS_CACHE_HOURS * 3600
            )
            if (
                policy.checked_at
                and timezone.now() - policy.checked_at < max_age
                and policy.status != cls.Status.FAILED
            ):
                return policy
        return cls.fetch(domain)

    @classmethod
    def fetch(cls, domain):
        """Fetch the MTA-STS policy from the well-known HTTPS endpoint."""
        url = f"https://mta-sts.{domain}/.well-known/mta-sts.txt"
        now = timezone.now()
        try:
            response = httpx.get(url, timeout=10, follow_redirects=True)
            match response.status_code:
                case 404:
                    return cls.objects.update_or_create(
                        domain=domain,
                        defaults={
                            "status": cls.Status.NONE,
                            "policy_id": "",
                            "mode": "",
                            "max_age_secs": 0,
                            "mx_patterns": [],
                            "error": "",
                            "checked_at": now,
                        },
                    )[0]
                case _:
                    response.raise_for_status()
                    mode, policy_id, max_age, mx_patterns = "", "", 0, []
                    for line in response.text.splitlines():
                        if ":" not in line:
                            continue
                        key, value = (s.strip() for s in line.split(":", 1))
                        match key:
                            case "mode":
                                mode = value
                            case "stsid":
                                policy_id = value
                            case "max_age":
                                max_age = int(value)
                            case "mx":
                                mx_patterns.append(value)
                    return cls.objects.update_or_create(
                        domain=domain,
                        defaults={
                            "status": cls.Status.LOADED,
                            "policy_id": policy_id,
                            "mode": mode,
                            "max_age_secs": max_age,
                            "mx_patterns": mx_patterns,
                            "error": "",
                            "checked_at": now,
                        },
                    )[0]
        except Exception as e:  # noqa: BLE001 — HTTP, DNS, and parsing raise varied exceptions
            return cls.objects.update_or_create(
                domain=domain,
                defaults={
                    "status": cls.Status.FAILED,
                    "error": str(e),
                    "checked_at": now,
                },
            )[0]
