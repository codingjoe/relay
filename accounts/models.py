import secrets
import string

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


def generate_api_key():
    """Generate a 32-character random secret for use as an API key."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


class Organization(TimeStamped):
    slug = models.SlugField(
        _("slug"),
        max_length=255,
        unique=True,
        help_text=_("URL-safe identifier, lowercase letters, digits, and hyphens."),
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Membership",
        related_name="organizations",
    )

    def __str__(self):
        return self.slug

    def get_absolute_url(self):
        return reverse("accounts:org-home", kwargs={"org_slug": self.slug})


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
    role = models.TextField(
        _("role"),
        choices=Role,
        default=Role.WRITE,
        help_text=_(
            "Write members can use services. Admin members can also manage users."
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
    """Provide a required `org` foreign key for resources always owned by an organization.

    Use this mixin for resources that always belong to an org (for example,
    credentials). Resources that can be system-owned (for example, the free
    sender domain) keep their own nullable `org` foreign key instead.
    """

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="%(class)ss",
        help_text=_("Owning organization."),
    )

    class Meta:
        abstract = True


class CredentialQuerySet(models.QuerySet):
    def create_with_key(self, *, org, name="", **kwargs):
        """Create and persist a credential with a generated key.

        Return a `(credential, raw_key)` tuple. The caller sees the raw key
        only once.
        """
        raw_key = generate_api_key()
        credential = self.model(org=org, name=name, **kwargs)
        credential.set_key(raw_key)
        credential.save(force_insert=True)
        return credential, raw_key


class Credential(OrganizationOwned):
    """Abstract base for per-service credentials.

    The plaintext key is never stored: only a hash (like Django passwords).
    The key_prefix (the first 8 characters) makes an O(1) lookup possible
    before hash verification. Concrete models live in service apps (for
    example, smtp.SmtpCredential).
    """

    key_hash = models.CharField(
        _("key hash"),
        max_length=128,
        editable=False,
        help_text=_("Hashed key. The plaintext appears only once at creation."),
    )
    key_prefix = models.CharField(
        _("key prefix"),
        max_length=8,
        editable=False,
        help_text=_("First 8 characters, for display and O(1) lookup."),
    )
    name = models.CharField(
        _("name"),
        max_length=255,
        blank=True,
        help_text=_("Human-readable label."),
    )
    last_used_at = models.DateTimeField(
        _("last used"),
        null=True,
        blank=True,
        help_text=_("Last successful verification."),
    )
    hold = models.BooleanField(
        _("hold"),
        default=False,
        help_text=_("Suspended keys cannot be used."),
    )

    objects = CredentialQuerySet.as_manager()

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.org} / {self.name or self.key_prefix}…"

    @property
    def salt(self):
        """Return a stable salt unique to the concrete credential class."""
        return f"{self.__class__.__module__}.{self.__class__.__name__}"

    def set_key(self, raw_key):
        """Persist a one-way representation of the key.

        The caller sees the plaintext once. The plaintext is never stored.
        """
        self.key_hash = make_password(raw_key, self.salt)
        self.key_prefix = raw_key[:8]

    def verify_key(self, raw_key):
        """Verify the provided key against the stored credential.

        Records a successful verification as the last use, and returns whether
        the key matched.
        """
        if check_password(raw_key, self.key_hash):
            self.last_used_at = timezone.now()
            self.save(update_fields=["last_used_at", "modified_at"])
            return True
        return False
