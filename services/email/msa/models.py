import datetime
from enum import nonmember

from django.core.validators import validate_email
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_letter.fields import HashedEmailField

from abstract.models import TimeStamped
from accounts.models import Credential, OrganizationOwned
from services.email.message.models import Message
from services.email.spam.client import VirusAction

from .tasks import deliver_message


class TerminalStatusError(ValueError):
    """A write tried to move a message out of a final status."""

    def __init__(self, message_pk, stored_status, status):
        super().__init__(
            f"Message {message_pk} reached {stored_status} and cannot become {status}"
        )


class OutgoingMessageQuerySet(models.QuerySet):
    def release(self) -> int:
        """Release held spam messages and return how many moved."""
        with transaction.atomic():
            pks = list(
                self.select_for_update(skip_locked=True)
                .filter(
                    status=OutgoingMessage.Status.HELD,
                    virus_action=VirusAction.CLEAN,
                )
                .values_list("pk", flat=True)
            )
            if released := self.filter(pk__in=pks).update(
                status=OutgoingMessage.Status.PENDING,
                modified_at=timezone.now(),
            ):
                transaction.on_commit(
                    lambda: [deliver_message.enqueue(message_id=str(pk)) for pk in pks]
                )
        return released


class OutgoingMessage(Message):
    """Deliver outbound email submitted via the SMTP server."""

    class Status(models.TextChoices):
        PENDING = "pending", _("pending")
        SENT = "sent", _("sent")
        HELD = "held", _("held")
        BOUNCED = "bounced", _("bounced")
        DROPPED = "dropped", _("dropped")
        SUPPRESSED = "suppressed", _("suppressed")
        SANDBOXED = "sandboxed", _("sandboxed")
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
    is_sandbox = models.BooleanField(
        _("sandbox"),
        default=False,
        help_text=_(
            "Whether a sandbox credential submitted the message, which "
            "relay never transmits."
        ),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["-id"]

    objects = OutgoingMessageQuerySet.as_manager()

    email_url_name = "msa:message-detail"

    def __str__(self):
        return f"{self.mail_from} → {self.rcpt_to} ({self.status})"

    url_name = "message-detail"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__status = self.status

    @property
    def can_release(self) -> bool:
        """Return whether a held message may be sent after review."""
        return (
            self.status == self.Status.HELD and self.virus_action == VirusAction.CLEAN
        )

    def save(self, *args, **kwargs):
        """
        Refuse a status change on a message that already left pending.

        A late bounce DSN is the one exception. A DSN proves the recipient
        server accepted the message, so relay only learns after a message
        ended sent or failed that the remote refused it after all.
        """
        if self.status != self.__status and self.__status != self.Status.PENDING:
            allowed = (self.__status, self.status) in (
                (self.Status.SENT, self.Status.BOUNCED),
                (self.Status.FAILED, self.Status.BOUNCED),
            )
            if not allowed:
                raise TerminalStatusError(self.pk, self.__status, self.status)
        super().save(*args, **kwargs)
        self.__status = self.status


class MsaCredential(Credential):
    """Authenticate outgoing SMTP submissions for an organization."""

    class Type(models.TextChoices):
        SMTP = "smtp", _("SMTP")
        SMTP_IP = "smtp-ip", _("SMTP-IP")
        SANDBOX = "sandbox", _("Sandbox")

    type = models.TextField(
        _("type"),
        choices=Type,
        default=Type.SMTP,
        help_text=_(
            "Purpose of the credential. Sandbox credentials accept "
            "submissions without a delivery attempt."
        ),
    )


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
        salt="services.email.msa.models.SuppressionEntry",
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
        return f"{self.org} / {self.address_hash.hex()[:12]}… ({self.reason})"

    def __repr__(self):
        return f"<SuppressionEntry {self.pk}>"

    @classmethod
    def hash_address(cls, email) -> bytes:
        """Return the salted SHA-256 digest of a lowercased email address."""
        validate_email(email)
        return cls._meta.get_field("address_hash").hash_email(email)
