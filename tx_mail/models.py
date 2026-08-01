"""Common fields shared between inbound and outbound email messages."""

import uuid

from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


class Message(TimeStamped):
    """Concrete parent of inbound and outbound email messages.

    The shared RFC 5322 envelope and header fields live on this table.
    Per-direction data (delivery state, sender, receiving domain, …) lives
    on the concrete child models via multi-table inheritance.
    """

    class Kind(models.TextChoices):
        INCOMING = "incoming", _("incoming")
        OUTGOING = "outgoing", _("outgoing")

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
    kind = models.TextField(_("kind"), choices=Kind)
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
    received_at = models.DateTimeField(
        _("received at"),
        default=timezone.now,
        help_text=_("When the message was accepted."),
    )
    received_with_tls = models.BooleanField(
        _("received with TLS"),
        default=False,
        help_text=_("Submission received over TLS."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.kind})"

    def get_absolute_url(self) -> str:
        """Return the per-direction detail URL based on ``kind``."""
        match self.kind:
            case self.Kind.OUTGOING:
                view = "smtp:message-detail"
            case self.Kind.INCOMING:
                view = "mx:message-detail"
            case _:
                msg = f"unknown message kind: {self.kind}"
                raise ValueError(msg)
        return reverse(view, kwargs={"org_slug": self.org.slug, "pk": self.pk})
