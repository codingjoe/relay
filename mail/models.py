import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from domains.models import Credential, Domain


class Message(TimeStamped):
    class Scope(models.TextChoices):
        INCOMING = "incoming", _("incoming")
        OUTGOING = "outgoing", _("outgoing")

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        SENT = "sent", _("sent")
        DELIVERED = "delivered", _("delivered")
        HELD = "held", _("held")
        BOUNCED = "bounced", _("bounced")
        DROPPED = "dropped", _("dropped")
        FAILED = "failed", _("failed")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="messages",
        null=True,
        blank=True,
    )
    scope = models.CharField(
        _("scope"),
        max_length=8,
        choices=Scope.choices,
        help_text=_("Whether this message is incoming or outgoing."),
    )
    rcpt_to = models.TextField(
        _("to"),
        help_text=_("Recipient email address(es)."),
    )
    mail_from = models.EmailField(
        _("from"),
        help_text=_("Sender email address."),
    )
    subject = models.TextField(
        _("subject"),
        blank=True,
        help_text=_("Email subject line."),
    )
    message_id = models.TextField(
        _("message ID"),
        blank=True,
        help_text=_("SMTP Message-ID header value."),
    )
    received_at = models.DateTimeField(
        _("received at"),
        auto_now_add=True,
        help_text=_("When this message was received by the SMTP server."),
    )
    domain = models.ForeignKey(
        Domain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    credential = models.ForeignKey(
        Credential,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages",
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        help_text=_("Current delivery status of this message."),
    )
    size = models.PositiveBigIntegerField(
        _("size"),
        default=0,
        help_text=_("Message size in bytes."),
    )
    tag = models.CharField(
        _("tag"),
        max_length=255,
        blank=True,
        help_text=_("Optional tag for grouping messages."),
    )
    received_with_ssl = models.BooleanField(
        _("received with SSL"),
        default=False,
        help_text=_("Whether the message was received over a TLS connection."),
    )
    raw_body = models.FileField(
        _("raw body"),
        upload_to="mail/",
        blank=True,
        help_text=_("Raw .eml file for this message."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["sender", "scope", "status"]),
            models.Index(fields=["sender", "received_at"]),
            models.Index(fields=["domain", "status"]),
        ]

    def __str__(self):
        return f"{self.scope} {self.mail_from} → {self.rcpt_to} ({self.status})"


class Transmission(TimeStamped):
    """A message transmission event — ingress or egress attempt.

    Tracks the SMTP transaction for a message, whether receiving
    (ingress) or sending (egress).  Each message may have multiple
    transmissions (e.g. retry attempts).
    """

    class Status(models.TextChoices):
        SENT = "sent", _("sent")
        DELIVERED = "delivered", _("delivered")
        FAILED = "failed", _("failed")
        RETRY = "retry", _("retry")
        BOUNCED = "bounced", _("bounced")

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="transmissions",
    )
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status.choices,
        help_text=_("Transmission status for this attempt."),
    )
    code = models.PositiveIntegerField(
        _("code"),
        null=True,
        blank=True,
        help_text=_("SMTP response code from the remote server."),
    )
    output = models.TextField(
        _("output"),
        blank=True,
        help_text=_("Raw SMTP output from the remote server."),
    )
    details = models.TextField(
        _("details"),
        blank=True,
        help_text=_("Human-readable transmission details."),
    )
    sent_with_ssl = models.BooleanField(
        _("sent with SSL"),
        default=False,
        help_text=_("Whether this transmission was sent over TLS."),
    )
    log_id = models.CharField(
        _("log ID"),
        max_length=255,
        blank=True,
        help_text=_("Remote server log ID for this transmission."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.message} → {self.status}"
