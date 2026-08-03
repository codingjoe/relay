"""SMTP sending models — outgoing messages, transmissions, and credentials."""

import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Credential
from services.email.message.models import Message


class OutgoingMessage(Message):
    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        SENT = "sent", _("sent")
        DELIVERED = "delivered", _("delivered")
        HELD = "held", _("held")
        BOUNCED = "bounced", _("bounced")
        DROPPED = "dropped", _("dropped")
        FAILED = "failed", _("failed")

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="outgoing_messages",
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_messages",
    )
    credential = models.ForeignKey(
        "SmtpCredential",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_messages",
    )
    status = models.TextField(
        _("status"),
        choices=Status,
        default=Status.PENDING,
        help_text=_("Send/deliver lifecycle state."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["sender", "status"]),
            models.Index(fields=["domain", "status"]),
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
        return str(self.domain) if self.domain_id else ""

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
