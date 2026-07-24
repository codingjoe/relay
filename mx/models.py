"""MX ingress models — incoming messages, webhooks, and deliveries.

This app owns the incoming delivery path: the incoming message record,
webhook endpoints (with per-webhook receiving domain config), and webhook
delivery tracking. Domain configuration lives in the ``domains`` app.
"""

import base64
import hashlib
import uuid
from fnmatch import fnmatch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
)
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import OrganizationOwned


def fernet() -> Fernet:
    """Return a Fernet instance keyed by Django's SECRET_KEY."""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


class IncomingMessage(TimeStamped):
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
    mail_from = models.EmailField(
        _("from"),
        help_text=_("Envelope sender address (MAIL FROM)."),
    )
    rcpt_to = models.TextField(
        _("to"),
        help_text=_("Envelope recipient address(es) (RCPT TO)."),
    )
    subject = models.TextField(
        _("subject"),
        blank=True,
        help_text=_("RFC 5322 Subject header value."),
    )
    message_id = models.TextField(
        _("message ID"),
        blank=True,
        help_text=_("RFC 5322 Message-ID header."),
    )
    received_at = models.DateTimeField(
        _("received at"),
        auto_now_add=True,
        help_text=_("When the message was accepted via MX."),
    )
    received_with_tls = models.BooleanField(
        _("received with TLS"),
        default=False,
        help_text=_("Incoming delivery used STARTTLS."),
    )
    raw_body = models.FileField(
        _("raw body"),
        upload_to="incoming/",
        blank=True,
        help_text=_("Raw RFC 822 message bytes."),
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
    private_key = models.TextField(
        _("private key"),
        editable=False,
        help_text=_("Fernet-encrypted Ed25519 private key."),
    )
    public_key = models.TextField(
        _("public key"),
        editable=False,
        help_text=_("Ed25519 public key — share with clients to verify signatures."),
    )
    key_id = models.CharField(
        _("key ID"),
        max_length=16,
        editable=False,
        help_text=_("Short fingerprint of the public key."),
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
        """True if the receiving domain is the free sender domain managed by us."""
        return (
            self.receiving_domain_name.lower()
            == settings.RELAY_FREE_SENDER_DOMAIN.lower()
        )

    @property
    def mx_target(self) -> str:
        """The expected MX exchange hostname."""
        from domains.models import Domain

        receiving = self.receiving_domain_name.lower()
        parts = receiving.split(".")
        for i in range(len(parts)):
            candidate = ".".join(parts[i:])
            domain = Domain.objects.filter(name__iexact=candidate).first()
            if domain:
                return domain.sender_domain
        return f"{settings.RELAY_SENDER_SUBDOMAIN_PREFIX}.{receiving}"

    @property
    def mx_record(self) -> str:
        """The MX record the user needs to set (empty for free domain)."""
        if self.is_free_domain:
            return ""
        return f"MX {self.receiving_domain_name} → {self.mx_target}"

    def matches(self, rcpt_to) -> bool:
        """Return True if this webhook should fire for the given recipient."""
        return fnmatch(rcpt_to.lower(), self.address_pattern.lower())

    def generate_keypair(self):
        """Generate an Ed25519 keypair and store the private key encrypted."""
        private = Ed25519PrivateKey.generate()
        private_pem = private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public = private.public_key()
        public_pem = public.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()
        self.private_key = fernet().encrypt(private_pem).decode()
        self.public_key = public_pem
        self.key_id = hashlib.sha256(public_pem.encode()).hexdigest()[:16]

    def load_private_key(self) -> Ed25519PrivateKey:
        """Decrypt and return the Ed25519 private key."""
        private_pem = fernet().decrypt(self.private_key.encode())
        return serialization.load_pem_private_key(private_pem, password=None)

    @property
    def public_key_serialized(self) -> str:
        """Return the public key in Standard Webhooks ``whpk_`` format."""
        raw = serialization.load_pem_public_key(self.public_key.encode()).public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return f"whpk_{base64.b64encode(raw).decode()}"

    def sign(self, msg_id: str, timestamp: int, payload: bytes) -> str:
        """Sign a Standard Webhooks message and return ``v1a,{base64}``."""
        signed_content = f"{msg_id}.{timestamp}.".encode() + payload
        signature = self.load_private_key().sign(signed_content)
        return f"v1a,{base64.b64encode(signature).decode()}"


class WebhookDelivery(TimeStamped):
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
