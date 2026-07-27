"""Abstract models shared between ``IncomingMessage`` and ``OutgoingMessage``.

Both SMTP submissions and MX deliveries produce a message with the same
RFC 5322 envelope/header essentials. Keeping them in a single mixin avoids
field drift between the two message stores.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class MessageMixin(models.Model):
    class Meta:
        abstract = True

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
        auto_now_add=True,
        help_text=_("When the message was accepted."),
    )
    received_with_tls = models.BooleanField(
        _("received with TLS"),
        default=False,
        help_text=_("Submission received over TLS."),
    )
