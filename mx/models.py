"""MX ingress models — incoming messages, webhooks, and deliveries."""

import base64
import uuid
from fnmatch import fnmatch

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.messages import MessageMixin
from abstract.models import TimeStamped
from accounts.models import OrganizationOwned
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
        """Extract the domain from the address pattern (e.g. *@app.acme.com → app.acme.com)."""
        if "@" in self.address_pattern:
            return self.address_pattern.split("@", 1)[1]
        return self.address_pattern

    @property
    def is_free_domain(self) -> bool:
        """Report whether the receiving domain is the free sender domain managed by us."""
        return (
            self.receiving_domain_name.lower()
            == settings.RELAY_FREE_SENDER_DOMAIN.lower()
        )

    @property
    def mx_target(self) -> str:
        """Compute the MX exchange hostname senders should deliver to."""
        from domains.models import Domain

        receiving = self.receiving_domain_name.lower()
        if domain := Domain.objects.root_for(receiving).first():
            return domain.sender_domain
        return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{receiving}"

    @property
    def mx_record(self) -> str:
        """Describe the MX record the user must add (empty for free domains)."""
        if self.is_free_domain:
            return ""
        return f"MX {self.receiving_domain_name} → {self.mx_target}"

    def matches(self, rcpt_to) -> bool:
        """Match this webhook against a recipient address."""
        return fnmatch(rcpt_to.lower(), self.address_pattern.lower())

    @property
    def public_key_serialized(self) -> str:
        """Return the public key in Standard Webhooks ``whpk_`` format."""
        return f"whpk_{base64.b64encode(self.signing_key.public_bytes_raw()).decode()}"

    def sign(self, msg_id: str, timestamp: int, payload: bytes) -> str:
        """Sign a Standard Webhooks message and return ``v1a,{base64}``."""
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
