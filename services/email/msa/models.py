import datetime
import hashlib
from enum import nonmember

from django.core.validators import validate_email
from django.db import models
from django.db.models import Lookup
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped, Timing
from accounts.models import Credential, OrganizationOwned
from services.email.message.models import Message


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


class SpamCheck(Timing):
    """Record the wall-clock duration of a spam check."""

    message = models.ForeignKey(
        OutgoingMessage,
        on_delete=models.CASCADE,
        related_name="spam_checks",
    )
    score = models.FloatField(
        _("score"),
        null=True,
        blank=True,
        help_text=_("rspamd score the check returned, or null when the check failed."),
    )

    class Meta(Timing.Meta):
        ordering = ["started_at", "created_at"]
        verbose_name = _("spam check")

    @property
    def label(self) -> str:
        """Return the display name of this spam check."""
        name = str(self._meta.verbose_name)
        return f"{name} ({self.score})" if self.score is not None else name

    TIMELINE_VARIANT_COLORS = {
        "success": "var(--color-chart-green)",
        "warning": "var(--color-chart-yellow)",
        "destructive": "var(--color-chart-red)",
    }

    @property
    def event(self) -> dict:
        """Return one profile chart event for this spam check."""
        return {
            "name": self.label,
            "color": self.TIMELINE_VARIANT_COLORS.get(
                self.message.spam_badge_variant, "var(--color-chart-gray)"
            ),
            "start": int(self.started_at.timestamp() * 1000),
            "end": int(self.finished_at.timestamp() * 1000),
            "ips": "",
            "tls": "",
            "transcript": "",
            "score": self.score,
        }


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
