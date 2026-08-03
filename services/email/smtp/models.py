import uuid
from enum import nonmember

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Credential
from services.email.message.models import Message


class OutgoingMessage(Message):
    """Deliver outbound email submitted via the SMTP server."""

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        SENT = "sent", _("sent")
        DELIVERED = "delivered", _("delivered")
        HELD = "held", _("held")
        BOUNCED = "bounced", _("bounced")
        DROPPED = "dropped", _("dropped")
        FAILED = "failed", _("failed")
        DEFAULT = nonmember("pending")

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="outgoing_messages",
    )
    credential = models.ForeignKey(
        "SmtpCredential",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_messages",
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]

    @property
    def status_badge_variant(self) -> str:
        match self.status:
            case self.Status.SENT | self.Status.DELIVERED:
                return "primary"
            case self.Status.BOUNCED | self.Status.DROPPED | self.Status.FAILED:
                return "destructive"
            case _:
                return "outline"

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    def get_absolute_url(self):
        return reverse(
            "smtp:message-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.id},
        )


class Transmission(TimeStamped):
    """Track a single delivery attempt for an outgoing message.

    Each message can have multiple transmissions (for example, retry attempts).
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
        OutgoingMessage,
        on_delete=models.CASCADE,
        related_name="transmissions",
    )
    status = models.TextField(
        _("status"),
        choices=Status,
        help_text=_("Outcome of this delivery attempt."),
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
        help_text=_("Raw SMTP transcript from the remote server."),
    )
    details = models.TextField(
        _("details"),
        blank=True,
        help_text=_("Human-readable explanation of the outcome."),
    )
    sent_with_ssl = models.BooleanField(
        _("sent with SSL"),
        default=False,
        help_text=_("Delivered over TLS."),
    )
    log_id = models.TextField(
        _("log ID"),
        blank=True,
        help_text=_("Remote server log identifier."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]

    @property
    def status_badge_variant(self) -> str:
        match self.status:
            case self.Status.SENT | self.Status.DELIVERED:
                return "primary"
            case self.Status.FAILED | self.Status.BOUNCED:
                return "destructive"
            case _:
                return "outline"

    def __str__(self):
        return f"{self.message} → {self.status}"


class SmtpCredential(Credential):
    """Authenticate outgoing SMTP submissions for an organization."""

    class Type(models.TextChoices):
        SMTP = "smtp", _("SMTP")
        SMTP_IP = "smtp-ip", _("SMTP-IP")

    type = models.TextField(
        _("type"),
        choices=Type,
        default=Type.SMTP,
        help_text=_("SMTP authentication method."),
    )
