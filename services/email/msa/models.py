import datetime
import hashlib
import uuid
from enum import nonmember

from django.core.validators import validate_email
from django.db import models
from django.db.models import Lookup
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Credential, OrganizationOwned
from services.email.message.models import Message


class OutgoingMessage(Message):
    """Deliver outbound email submitted via the SMTP server."""

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        SENT = "sent", _("sent")
        DELIVERED = "delivered", _("delivered")
        HELD = "held", _("held")
        BOUNCED = "bounced", _("bounced")
        DROPPED = "dropped", _("dropped")
        SUPPRESSED = "suppressed", _("suppressed")
        FAILED = "failed", _("failed")
        DEFAULT = nonmember("pending")

        @property
        def badge_variant(self) -> str:
            Status = type(self)
            match self:
                case Status.SENT | Status.DELIVERED:
                    return "primary"
                case Status.BOUNCED | Status.DROPPED | Status.FAILED:
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

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    def get_absolute_url(self):
        return reverse(
            "msa:message-detail",
            kwargs={"org_slug": self.org.slug, "pk": self.id},
        )

    @property
    def spam_badge_variant(self) -> str:
        """Return the badge variant for the rspamd verdict."""
        return "destructive" if self.spam_action in {"reject", "drop"} else "outline"


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

    @property
    def status_badge_variant(self) -> str:
        match self.status:
            case self.Status.SENT | self.Status.DELIVERED:
                return "primary"
            case self.Status.FAILED | self.Status.BOUNCED:
                return "destructive"
            case _:
                return "outline"

    def __str__(self):
        return f"{self.message} → {self.status}"


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
        """Check whether an email is suppressed for the given org.

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
    """Store a salted hash of an email address that should not receive mail.

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
