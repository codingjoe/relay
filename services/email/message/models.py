import uuid
from email import message_from_bytes
from email.header import Header, decode_header

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


class Message(TimeStamped):
    """Base class for inbound and outbound email messages."""

    url_name: str
    """URL pattern name of the concrete subclass detail view in its own app."""

    email_url_name = ""
    """Fully qualified URL name of the view rendering the email itself.

    Concrete subclasses whose detail view does not render the email, for
    example report messages, point this at their incoming message view.
    """

    icon = ""
    """Lucide icon name of the concrete subclass. Falls back to the direction icons."""

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
    headers = models.JSONField(
        _("headers"),
        default=list,
        blank=True,
        help_text=_("RFC 5322 header fields of the message, as [name, value] pairs."),
    )
    received_with_tls = models.BooleanField(
        _("received with TLS"),
        default=False,
        help_text=_("Submission received over TLS."),
    )
    spam_score = models.FloatField(
        _("spam score"),
        null=True,
        blank=True,
        help_text=_("rspamd score assigned to the message."),
    )
    spam_action = models.TextField(
        _("spam action"),
        blank=True,
        choices=[
            ("pass", _("pass")),
            ("no action", _("no action")),
            ("greylist", _("greylist")),
            ("add header", _("add header")),
            ("rewrite subject", _("rewrite subject")),
            ("soft reject", _("soft reject")),
            ("reject", _("reject")),
            ("drop", _("drop")),
        ],
        help_text=_("rspamd action assigned to the message."),
    )

    class Status(models.TextChoices):
        """Base status choices. Subclasses must override and set DEFAULT."""

    status = models.TextField(
        _("status"),
        help_text=_("Delivery lifecycle state."),
    )
    domain = models.ForeignKey(
        "domains.Domain",
        on_delete=models.PROTECT,
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
    def kind_display(self) -> str:
        """Return the human-readable name of the concrete subclass."""
        return self.content_type.name

    @property
    def kind_icon(self) -> str:
        """
        Return the matching Lucide icon name.

        Reads the icon from the concrete class because multi-table
        inheritance returns base instances in shared querysets.
        """
        if icon := self.content_type.model_class().icon:
            return icon
        return "send" if self.kind == "outgoingmessage" else "inbox"

    @property
    def domain_name(self) -> str:
        """Return the associated domain name."""
        return str(self.domain) if self.domain_id else ""

    @property
    def status_badge_variant(self) -> str:
        """Return the basecoat badge variant for the status."""
        status_class = self.content_type.model_class().Status
        return status_class(self.status).badge_variant

    @property
    def spam_badge_variant(self) -> str:
        """Map the rspamd verdict to a badge variant."""
        match self.spam_action:
            case "pass" | "no action":
                return "success"
            case "greylist" | "add header" | "rewrite subject":
                return "warning"
            case "reject" | "soft reject" | "drop":
                return "destructive"
            case _:
                return "outline"

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.kind})"

    def get_absolute_url(self) -> str:
        model = self.content_type.model_class()
        return reverse(
            f"{self.content_type.app_label}:{model.url_name}",
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    def get_email_url(self) -> str:
        """
        Return the URL of the view rendering the email itself.

        Reads the URL name from the concrete class because multi-table
        inheritance returns base instances in shared querysets.
        """
        model = self.content_type.model_class()
        if not model.email_url_name:
            return self.get_absolute_url()
        return reverse(
            model.email_url_name,
            kwargs={"org_slug": self.org.slug, "pk": self.pk},
        )

    @classmethod
    def status_choices(cls) -> list[tuple[str, str]]:
        """Return status choices collected from all concrete subclasses."""
        choices = {
            value: label
            for subclass in cls.__subclasses__()
            for value, label in subclass.Status.choices
        }
        return sorted(choices.items(), key=lambda choice: str(choice[1]))

    def parsed_email(self):
        """Parse the raw body into an `email.message.Message` object."""
        try:
            self.raw_body.seek(0)
            return message_from_bytes(self.raw_body.read())
        except FileNotFoundError, ValueError:
            # FieldFile raises ValueError when no file is associated (empty
            # name), e.g. pruned or fixture-only rows.
            return message_from_bytes(b"body pruned")

    def raw_bytes(self) -> bytes:
        """Return the stored message content, or empty bytes when pruned."""
        try:
            self.raw_body.seek(0)
            return self.raw_body.read()
        except FileNotFoundError, ValueError:
            return b""

    @property
    def text_body(self) -> bytes:
        """
        Return the decoded text payload of the stored body.

        Multipart messages yield their first text part. Messages whose
        raw body is pruned or unreadable have no text payload.
        """
        if not self.raw_bytes():
            return b""
        return next(
            (
                payload
                for part in self.parsed_email().walk()
                if not part.is_multipart()
                and part.get_content_type().startswith("text/")
                and (payload := part.get_payload(decode=True)) is not None
            ),
            b"",
        )

    @classmethod
    def headers_from_raw(cls, raw_bytes):
        """Return the message headers as JSON-serializable [name, value] pairs."""
        return [
            [cls.header_to_text(name), cls.header_to_text(value)]
            for name, value in message_from_bytes(raw_bytes).items()
        ]

    @staticmethod
    def header_to_text(value) -> str:
        """
        Return a parsed header name or value as a JSON-serializable string.

        The compat32 parser returns `Header` objects for header values with
        raw 8-bit bytes, which a JSONField cannot serialize. Decode those
        back to text. Replace NUL bytes with U+FFFD because PostgreSQL
        jsonb rejects them in any representation; the raw body keeps the
        byte-exact form.
        """
        if isinstance(value, Header):
            text = b"".join(
                chunk if isinstance(chunk, bytes) else chunk.encode()
                for chunk, _ in decode_header(value)
            ).decode("utf-8", "replace")
        else:
            text = value
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                # 8-bit header names carry surrogate escapes, not real code points.
                text = text.encode("utf-8", "surrogateescape").decode(
                    "utf-8", "replace"
                )
        # PostgreSQL jsonb rejects NUL bytes in any representation.
        return text.replace("\x00", "\ufffd")

    @property
    def parsed_headers(self):
        """Return the message headers as [name, value] pairs, from storage or the raw body."""
        if self.headers:
            return self.headers
        try:
            self.raw_body.seek(0)
            return self.headers_from_raw(self.raw_body.read())
        except FileNotFoundError, ValueError:
            return []
