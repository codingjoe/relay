import datetime
import hashlib
import uuid
from enum import nonmember

from django.core.validators import validate_email
from django.db import models
from django.db.models import Lookup
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import FetchPeersManager, TimeStamped, Timing
from accounts.models import Credential, OrganizationOwned
from kms.models import Certificate
from services.email.message.models import Message
from services.email.tls import parse_peer_certificates


class OutgoingMessage(Message):
    """Deliver outbound email submitted via the SMTP server."""

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        SENT = "sent", _("sent")
        HELD = "held", _("held")
        BOUNCED = "bounced", _("bounced")
        DROPPED = "dropped", _("dropped")
        SUPPRESSED = "suppressed", _("suppressed")
        FAILED = "failed", _("failed")
        DEFAULT = nonmember("pending")

        @property
        def badge_variant(self) -> str:
            status_class = type(self)
            match self:
                case status_class.SENT:
                    return "success"
                case status_class.HELD:
                    return "warning"
                case status_class.BOUNCED | status_class.DROPPED | status_class.FAILED:
                    return "destructive"
                case _:
                    return "outline"

    credential = models.ForeignKey(
        "MsaCredential",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_messages",
    )
    feedback_id = models.TextField(
        _("Feedback-ID"),
        blank=True,
        default="",
        db_index=True,
        help_text=_(
            "Feedback-ID header relay minted for this message. Providers "
            "echo it in FBL complaints, proving per-message identity when "
            "they do not echo the VERP envelope sender."
        ),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]

    email_url_name = "msa:message-detail"

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    url_name = "message-detail"


class Transmission(Timing):
    """
    Track a single SMTP leg of an outgoing message.

    Each message starts with the submission to relay's MSA and can gain
    multiple delivery transmissions (for example, retry attempts).
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted", _("submitted")
        SENT = "sent", _("sent")
        FAILED = "failed", _("failed")
        RETRY = "retry", _("retry")
        BOUNCED = "bounced", _("bounced")

    class TlsMode(models.TextChoices):
        PLAINTEXT = "plaintext", "plaintext"
        STARTTLS = "starttls", "STARTTLS"
        TLS = "tls", "TLS"

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
    mx_host = models.TextField(
        _("MX host"),
        blank=True,
        help_text=_("MX hostname this delivery attempt dialed."),
    )
    sending_mta_ip_address = models.GenericIPAddressField(
        _("sending MTA IP address"),
        null=True,
        blank=True,
        help_text=_("IP address relay sent this delivery attempt from."),
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
        help_text=_("TLS transport negotiated for this delivery attempt."),
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
    started_at = models.DateTimeField(
        _("started"),
        help_text=_("When this transmission leg started."),
    )
    finished_at = models.DateTimeField(
        _("finished"),
        help_text=_("When this transmission leg ended."),
    )

    objects = FetchPeersManager()

    class Meta(TimeStamped.Meta):
        ordering = ["-created_at"]

    @classmethod
    def record_submission(cls, message, ssl, started_at, client_ip=None):
        """Record the submission relay accepted for a message."""
        ssl_object = ssl.get("ssl_object") if isinstance(ssl, dict) else None
        cipher = ssl_object.cipher() if ssl_object else None
        if isinstance(ssl, dict):
            tls_mode = cls.TlsMode.STARTTLS
        elif ssl:
            tls_mode = cls.TlsMode.TLS
        else:
            tls_mode = cls.TlsMode.PLAINTEXT
        cls.objects.create(
            message=message,
            status=cls.Status.SUBMITTED,
            code=250,
            output="250 OK",
            tls_mode=tls_mode,
            tls_version=cipher[1] if cipher else "",
            tls_cipher=cipher[0] if cipher else "",
            tls_certificate=(
                Certificate.store_presented_chain(parse_peer_certificates(ssl_object))
                if ssl_object
                else None
            ),
            submission_ip_address=client_ip,
            started_at=started_at,
            finished_at=timezone.now(),
        )

    @property
    def status_badge_variant(self) -> str:
        match self.status:
            case self.Status.SENT:
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

    def __str__(self):
        return f"{self.message} → {self.status}"


class SpamCheck(Timing):
    """Record the wall-clock duration of a spam check."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    message = models.ForeignKey(
        OutgoingMessage,
        on_delete=models.CASCADE,
        related_name="spam_checks",
    )
    started_at = models.DateTimeField(
        _("started"),
        help_text=_("When the spam check started."),
    )
    finished_at = models.DateTimeField(
        _("finished"),
        help_text=_("When the spam check finished."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["started_at", "created_at"]
        indexes = [models.Index(fields=["message", "started_at"])]
        verbose_name = _("spam check")


class MsaCredential(Credential):
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


class EmailLookup(Lookup):
    """Hash an email address before comparing against `address_hash`."""

    lookup_name = "email"

    def as_sql(self, compiler, connection):
        lhs, lhs_params = self.process_lhs(compiler, connection)
        model = self.lhs.output_field.model
        return f"{lhs} = %s", [*lhs_params, model.hash_address(self.rhs)]


class HashedEmailField(models.TextField):
    """Provide the `__email` lookup for address hashing."""


HashedEmailField.register_lookup(EmailLookup)


class SuppressionQuerySet(models.QuerySet):
    def create_or_update(self, defaults=None, **kwargs):
        email = kwargs.pop("email", None)
        if email is not None:
            kwargs["address_hash"] = self.model.hash_address(email)
        defaults = defaults or {}
        if "reason" in kwargs:
            defaults["reason"] = kwargs.pop("reason")
        return self.update_or_create(defaults=defaults, **kwargs)

    def is_suppressed(self, org, email) -> bool:
        """
        Check whether an email is suppressed for the given org.

        All entries for the current org suppress regardless of age or reason.
        Bounce entries from any other org suppress for 30 days after creation.
        """
        bounce_cutoff = timezone.now() - datetime.timedelta(days=30)
        return (
            self.filter(
                address_hash=self.model.hash_address(email),
            )
            .filter(
                models.Q(org=org)
                | models.Q(
                    reason=self.model.Reason.BOUNCE,
                    created_at__gte=bounce_cutoff,
                ),
            )
            .exists()
        )


class SuppressionEntry(OrganizationOwned):
    """
    Store a salted hash of an email address that should not receive mail.

    The plain email address is never stored. Bounces are added automatically;
    users can add or remove entries manually. Use the `__email` lookup to
    filter by email address:

        SuppressionEntry.objects.filter(org=org, address_hash__email=email)
    """

    class Reason(models.TextChoices):
        BOUNCE = "bounce", _("bounce")
        MANUAL = "manual", _("manual")

    address_hash = HashedEmailField(
        _("address hash"),
        help_text=_("Salted SHA-256 of the lowercased email address."),
    )
    reason = models.TextField(
        _("reason"),
        choices=Reason,
        default=Reason.MANUAL,
        help_text=_("How the entry was added."),
    )

    objects = SuppressionQuerySet.as_manager()

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["org", "address_hash"],
                name="unique_suppression_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.org} / {self.address_hash[:12]}… ({self.reason})"

    @classmethod
    def salt(cls) -> str:
        """Return a stable salt unique to this model class."""
        return f"{cls.__module__}.{cls.__name__}"

    @classmethod
    def hash_address(cls, email) -> str:
        """Return the salted SHA-256 hex digest of a lowercased email address."""
        validate_email(email)
        return hashlib.sha256((cls.salt() + email.lower()).encode()).hexdigest()
