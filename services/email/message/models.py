import uuid
from email import message_from_bytes

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
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

    class Status(models.TextChoices):
        """Base status choices. Subclasses must override and set DEFAULT."""

    status = models.TextField(
        _("status"),
        help_text=_("Delivery lifecycle state."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.CASCADE,
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
        if not self._is_pk_set():
            self.content_type = ContentType.objects.get_for_model(type(self))
            if not self.status:
                self.status = self.Status.DEFAULT
        self.clean_status()
        super().save(*args, **kwargs)

    def clean_status(self):
        if self.status not in self.Status.values:
            raise ValidationError(
                _("Invalid status value: %(value)s"), params={"value": self.status}
            )

    @property
    def status_display(self) -> str:
        """Return a human-readable label for the status."""
        return self.content_type.model_class().Status(self.status).label

    @property
    def kind(self) -> str:
        return self.content_type.model

    @property
    def kind_icon(self) -> str:
        """Return the matching Lucide icon name."""
        return "send" if self.kind == "outgoingmessage" else "inbox"

    @property
    def domain_name(self) -> str:
        """Return the associated domain name."""
        return str(self.domain)

    @property
    def status_badge_variant(self) -> str:
        """Return the basecoat badge variant for the status."""
        Status = self.content_type.model_class().Status
        return Status(self.status).badge_variant

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.kind})"

    def get_absolute_url(self) -> str:
        child = self.content_type.get_object_for_this_type(pk=self.pk)
        return child.get_absolute_url()

    def parsed_email(self):
        """Parse the raw body into an `email.message.Message` object."""
        try:
            return message_from_bytes(self.raw_body.read())
        except FileNotFoundError:
            return message_from_bytes(b"body pruned")
