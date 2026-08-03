"""Shared message model for inbound and outbound email."""

import uuid
from email import message_from_bytes

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


class Message(TimeStamped):
    """Base class for inbound and outbound email messages."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    org = models.ForeignKey(
        "accounts.Organization",
        on_delete=models.CASCADE,
        related_name="+",
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
        editable=False,
    )
    mail_from = models.EmailField(
        _("mail from"),
        help_text=_("Envelope sender address (MAIL FROM)."),
    )
    rcpt_to = models.TextField(
        _("rcpt to"),
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
    raw_body = models.FileField(
        _("raw body"),
        upload_to="messages/",
        blank=True,
        help_text=_("Raw RFC 822 message bytes."),
    )
    received_with_tls = models.BooleanField(
        _("received with TLS"),
        default=False,
        help_text=_("Submission received over TLS."),
    )
    status = models.TextField(
        _("status"),
        default="",
        help_text=_("Delivery lifecycle state."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_("Domain associated with this message."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["domain", "status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.content_type_id:
            self.content_type = ContentType.objects.get_for_model(type(self))
        super().save(*args, **kwargs)

    @property
    def kind(self) -> str:
        return self.content_type.model

    @property
    def kind_icon(self) -> str:
        """Return the Lucide icon name for this message kind."""
        return "send" if self.kind == "outgoingmessage" else "inbox"

    @property
    def domain_name(self) -> str:
        """Return the associated domain name."""
        return str(self.domain) if self.domain_id else ""

    @property
    def status_badge_variant(self) -> str:
        """Return the basecoat badge variant for the status."""
        return "outline"

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.kind})"

    def get_absolute_url(self) -> str:
        child = self.content_type.get_object_for_this_type(pk=self.pk)
        return child.get_absolute_url()

    def parsed_email(self):
        """Parse the raw body into an :class:`email.message.Message` object."""
        try:
            return message_from_bytes(self.raw_body.read())
        except FileNotFoundError:
            return message_from_bytes(b"body pruned")
