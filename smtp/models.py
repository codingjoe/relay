"""SMTP sending models — outgoing messages, transmissions, and credentials.

This app owns the entire sending path: the message record, delivery
transmissions, and the SMTP credentials used to authenticate submissions.
Incoming (MX) mail lives in the separate ``mx`` app.
"""

import uuid

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Credential


class OutgoingMessage(TimeStamped):
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
        related_name="outgoing_messages",
    )
    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="outgoing_messages",
        help_text=_("Owning organization."),
    )
    rcpt_to = models.TextField(
        _("to"),
        help_text=_("Envelope recipient address(es) (RCPT TO)."),
    )
    mail_from = models.EmailField(
        _("from"),
        help_text=_("Envelope sender address (MAIL FROM)."),
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
        help_text=_("When the submission was accepted."),
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
    status = models.CharField(
        _("status"),
        max_length=10,
        choices=Status,
        default=Status.PENDING,
        help_text=_("Send/deliver lifecycle state."),
    )
    received_with_ssl = models.BooleanField(
        _("received with SSL"),
        default=False,
        help_text=_("Submission received over TLS."),
    )
    raw_body = models.FileField(
        _("raw body"),
        upload_to="mail/",
        blank=True,
        help_text=_("Raw RFC 822 message bytes."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["sender", "status"]),
            models.Index(fields=["sender", "received_at"]),
            models.Index(fields=["domain", "status"]),
        ]

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    def get_absolute_url(self):
        return reverse(
            "smtp:message-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.id},
        )


class Transmission(TimeStamped):
    """Track a single delivery attempt for an outgoing message.

    Each message may have multiple transmissions (e.g. retry attempts).
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
    status = models.CharField(
        _("status"),
        max_length=10,
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
    log_id = models.CharField(
        _("log ID"),
        max_length=255,
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

    type = models.CharField(
        _("type"),
        max_length=7,
        choices=Type,
        default=Type.SMTP,
        help_text=_("SMTP authentication method."),
    )
