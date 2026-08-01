"""Common fields shared between inbound and outbound email messages."""

import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


class Message(TimeStamped):
    """Parent of inbound and outbound email messages."""

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

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]

    @property
    def kind(self) -> str:
        return self.content_type.model

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.kind})"

    def get_absolute_url(self) -> str:
        match self.content_type.model:
            case "outgoingmessage":
                view = "smtp:message-detail"
            case "incomingmessage":
                view = "mx:message-detail"
            case _:
                msg = f"unknown message type: {self.content_type.model}"
                raise ValueError(msg)
        return reverse(view, kwargs={"org_slug": self.org.slug, "pk": self.pk})
