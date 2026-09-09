import uuid
from email import message_from_bytes
from email.header import Header, decode_header

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import FetchPeersManager, TimeStamped, Timing
from kms.models import Certificate
from services.email.tls import parse_peer_certificates


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
        help_text=_("Subject header value with RFC 2047 encoded-words decoded."),
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

    @property
    def headers_text(self) -> str:
        """Return the message headers as RFC 5322 header lines."""
        return "\n".join(f"{name}: {value}" for name, value in self.parsed_headers)


TIMELINE_COLORS = {
    "submitted": "var(--color-chart-blue)",
    "received": "var(--color-chart-blue)",
    "sent": "var(--color-chart-green)",
    "retry": "var(--color-chart-yellow)",
    "failed": "var(--color-chart-red)",
    "bounced": "var(--color-chart-red)",
}


class Transmission(Timing):
    """
    Track a single SMTP leg of a message.

    An incoming message starts with the reception on relay's MTA, an
    outgoing message starts with the submission to relay's MSA and can
    gain multiple delivery transmissions (for example, retry attempts).
    """

    class Status(models.TextChoices):
        RECEIVED = "received", _("received")
        SUBMITTED = "submitted", _("submitted")
        SENT = "sent", _("sent")
        FAILED = "failed", _("failed")
        RETRY = "retry", _("retry")
        BOUNCED = "bounced", _("bounced")

    class TlsMode(models.TextChoices):
        PLAINTEXT = "plaintext", "plaintext"
        STARTTLS = "starttls", "STARTTLS"
        TLS = "tls", "TLS"

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="transmissions",
    )
    mx_host = models.TextField(
        _("MX host"),
        blank=True,
        help_text=_("MX hostname this delivery attempt dialed."),
    )
    sending_mta_ip_address = models.GenericIPAddressField(
        _("sending MTA IP address"),
        null=True,
        blank=True,
        help_text=_("IP address the sending MTA used for this leg."),
    )
    receiving_mx_ip_address = models.GenericIPAddressField(
        _("receiving MX IP address"),
        null=True,
        blank=True,
        help_text=_("IP address of the MX that handled this delivery attempt."),
    )
    submission_ip_address = models.GenericIPAddressField(
        _("submission IP address"),
        null=True,
        blank=True,
        help_text=_("IP address that submitted this message to relay's MSA."),
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
    tls_mode = models.TextField(
        _("TLS mode"),
        choices=TlsMode,
        default=TlsMode.PLAINTEXT,
        help_text=_("TLS transport negotiated for this leg."),
    )
    tls_version = models.TextField(
        _("TLS version"),
        blank=True,
        help_text=_("Negotiated TLS protocol version, for example TLSv1.3."),
    )
    tls_cipher = models.TextField(
        _("TLS cipher"),
        blank=True,
        help_text=_("Negotiated TLS cipher suite."),
    )
    tls_certificate = models.ForeignKey(
        "kms.Certificate",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="transmissions",
    )
    log_id = models.TextField(
        _("log ID"),
        blank=True,
        help_text=_("Remote server log identifier."),
    )

    objects = FetchPeersManager()

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]

    @classmethod
    def tls_session_fields(cls, ssl):
        """Return the TLS field values negotiated for an SMTP session."""
        ssl_object = ssl.get("ssl_object") if isinstance(ssl, dict) else None
        cipher = ssl_object.cipher() if ssl_object else None
        if isinstance(ssl, dict):
            tls_mode = cls.TlsMode.STARTTLS
        elif ssl:
            tls_mode = cls.TlsMode.TLS
        else:
            tls_mode = cls.TlsMode.PLAINTEXT
        return {
            "tls_mode": tls_mode,
            "tls_version": cipher[1] if cipher else "",
            "tls_cipher": cipher[0] if cipher else "",
            "tls_certificate": (
                Certificate.store_presented_chain(parse_peer_certificates(ssl_object))
                if ssl_object
                else None
            ),
        }

    @classmethod
    def record_submission(cls, message, ssl, started_at, client_ip=None):
        """Record the submission relay accepted for a message."""
        cls.objects.create(
            message=message,
            status=cls.Status.SUBMITTED,
            code=250,
            output="250 OK",
            **cls.tls_session_fields(ssl),
            submission_ip_address=client_ip,
            started_at=started_at,
            finished_at=timezone.now(),
        )

    @classmethod
    def record_reception(cls, message, ssl, started_at, client_ip=None):
        """Record the SMTP session that delivered an inbound message."""
        cls.objects.create(
            message=message,
            status=cls.Status.RECEIVED,
            code=250,
            output="250 OK",
            **cls.tls_session_fields(ssl),
            sending_mta_ip_address=client_ip or None,
            started_at=started_at,
            finished_at=timezone.now(),
        )

    @property
    def status_badge_variant(self) -> str:
        match self.status:
            case self.Status.SENT | self.Status.RECEIVED:
                return "success"
            case self.Status.FAILED | self.Status.BOUNCED:
                return "destructive"
            case _:
                return "outline"

    @property
    def label(self) -> str:
        """Return the display name of this transmission."""
        target = self.mx_host or self.submission_ip_address or ""
        name = self.get_status_display()
        return f"{name} ({target})" if target else name

    @property
    def event(self) -> dict:
        """Return one profile chart event for this transmission."""
        tls = " · ".join(
            part
            for part in (
                self.get_tls_mode_display(),
                self.tls_version,
                self.tls_cipher,
            )
            if part
        )
        return {
            "name": self.label,
            "color": TIMELINE_COLORS[self.status],
            "start": int(self.started_at.timestamp() * 1000),
            "end": int(self.finished_at.timestamp() * 1000),
            "ips": (
                f"{self.sending_mta_ip_address or '-'} →"
                f" {self.receiving_mx_ip_address or '-'}"
                if (self.sending_mta_ip_address or self.receiving_mx_ip_address)
                else ""
            ),
            "tls": tls,
            "transcript": (
                f"transcript-{self.pk}"
                if self.output or self.details or self.log_id
                else ""
            ),
        }

    def __str__(self):
        return f"{self.message} → {self.status}"
