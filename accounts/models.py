"""Account models — organizations, memberships, and abstract credentials.

Organizations own resources (domains, credentials) — not individual users.
Each user gets a personal organization on signup. Members share access to
all org resources. Credentials are hashed and shown only once at creation.

Concrete credential models live in service apps (e.g. mail.SmtpCredential).
"""

import secrets
import string

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


def generate_api_key():
    """Generate a random 32-character API key."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


class Organization(TimeStamped):
    name = models.CharField(
        _("name"),
        max_length=255,
        help_text=_("Organization display name."),
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Membership",
        related_name="organizations",
    )

    def __str__(self):
        return self.name


class Membership(TimeStamped):
    class Role(models.TextChoices):
        WRITE = "write", _("write")
        ADMIN = "admin", _("admin")

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        _("role"),
        max_length=5,
        choices=Role.choices,
        default=Role.WRITE,
        help_text=_(
            "Write members can use services; admin members can also manage users."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["org", "user"],
                name="unique_membership",
            ),
        ]

    def __str__(self):
        return f"{self.user} @ {self.org} ({self.role})"


class OrganizationOwned(TimeStamped):
    """Abstract base for resources owned by an organization.

    Concrete org-owned models (Domain, SmtpCredential) inherit this so the
    `org` foreign key and its conventions live in one place. `org` is nullable
    to allow system-owned objects (e.g. the free sender domain).
    """

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        null=True,
        blank=True,
        help_text=_("Organization that owns this resource; null for system objects."),
    )

    class Meta:
        abstract = True


class CredentialQuerySet(models.QuerySet):
    def create_with_key(self, *, org, name="", **kwargs):
        """Create a credential with a generated key. Returns (credential, raw_key)."""
        raw_key = generate_api_key()
        credential = self.model(org=org, name=name, **kwargs)
        credential.set_key(raw_key)
        credential.save(force_insert=True)
        return credential, raw_key


class Credential(OrganizationOwned):
    """Abstract base for per-service credentials.

    The plaintext key is never stored — only a hash (like Django passwords).
    The key_prefix (first 8 chars) enables O(1) lookup before hash verification.
    Concrete models live in service apps (e.g. mail.SmtpCredential).
    """

    key_hash = models.CharField(
        _("key hash"),
        max_length=128,
        editable=False,
        help_text=_("Hashed key — plaintext is shown only once at creation."),
    )
    key_prefix = models.CharField(
        _("key prefix"),
        max_length=8,
        editable=False,
        help_text=_("First 8 characters for display and lookup."),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        blank=True,
        help_text=_("Human-readable label for this credential."),
    )
    last_used_at = models.DateTimeField(
        _("last used"),
        null=True,
        blank=True,
        help_text=_("When this key was last used for authentication."),
    )
    hold = models.BooleanField(
        _("hold"),
        default=False,
        help_text=_("If true, this key is suspended and cannot be used."),
    )

    objects = CredentialQuerySet.as_manager()

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.org} / {self.name or self.key_prefix}…"

    @property
    def salt(self):
        """Deterministic salt based on the concrete class module and name."""
        return f"{self.__class__.__module__}.{self.__class__.__name__}"

    def set_key(self, raw_key):
        """Hash and store the key. Caller must show raw_key to the user once."""
        self.key_hash = make_password(raw_key, self.salt)
        self.key_prefix = raw_key[:8]

    def verify_key(self, raw_key):
        """Return True if raw_key matches the stored hash, updating last_used_at."""
        if check_password(raw_key, self.key_hash):
            self.last_used_at = timezone.now()
            self.save(update_fields=["last_used_at", "modified_at"])
            return True
        return False
