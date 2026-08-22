import secrets
import string

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped


def generate_api_key():
    """Generate a 32-character random secret for use as an API key."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


organization_slug_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    message=_("Enter lowercase letters, digits, and single hyphens."),
    code="invalid",
)


class Organization(TimeStamped):
    slug = models.SlugField(
        _("slug"),
        max_length=63,
        unique=True,
        validators=[organization_slug_validator],
        help_text=_(
            "DNS-safe identifier, at most 63 lowercase letters, digits, and hyphens."
        ),
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Membership",
        related_name="organizations",
    )

    billing_is_active = True

    def __str__(self):
        return self.slug

    def save(self, *args, **kwargs):
        self.slug = self._meta.get_field("slug").clean(self.slug, self)
        return super().save(*args, **kwargs)

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
    credentials). Models that need a custom reverse relation define their own
    required `org` foreign key instead.
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

    The plaintext key is never stored. Only a hash (like Django passwords).
    The key_prefix (the first 8 characters) makes an O(1) lookup possible
    before hash verification. Concrete models live in service apps (for
    example, msa.MsaCredential).
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


class UserEncryptionKey(TimeStamped):
    """Store a user's X25519 public key and encrypted private key material.

    The private key is encrypted with the user's Master Key, which is in turn
    encrypted with a KEK derived from the user's encryption passphrase. The
    server never sees the passphrase, KEK, or Master Key. All derivation and
    decryption happen client-side in the browser.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="encryption_keys",
    )
    public_key = models.TextField(
        _("public key"),
        help_text=_("Base64-encoded X25519 public key."),
    )
    encrypted_master_key = models.TextField(
        _("encrypted master key"),
        help_text=_(
            "Master Key encrypted with the KEK derived from the user's "
            "encryption passphrase. Decrypted client-side only."
        ),
    )
    encrypted_private_key = models.TextField(
        _("encrypted private key"),
        help_text=_(
            "X25519 private key encrypted with the Master Key. "
            "Decrypted client-side only."
        ),
    )
    key_id = models.CharField(
        _("key ID"),
        max_length=16,
        editable=False,
        help_text=_("Short SHA256 fingerprint of the public key."),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key_id"],
                name="unique_user_encryption_key_id_per_user",
            ),
        ]

    def __str__(self):
        return f"{self.user} / {self.key_id}"

    def save(self, *args, **kwargs):
        if not self.key_id:
            from kms import envelope

            self.key_id = envelope.key_fingerprint(envelope.decode_key(self.public_key))
        super().save(*args, **kwargs)


class MembershipEncryptionKey(TimeStamped):
    """Distribute an org's private key to a member via sealed encryption.

    The org private key is sealed (encrypted) with the member's X25519 public
    key using crypto_box_seal. Only the member's private key can unseal it.
    Deleting this row revokes the member's ability to decrypt org files.
    """

    membership = models.OneToOneField(
        Membership,
        on_delete=models.CASCADE,
        related_name="encryption_key",
    )
    org_encryption_key = models.ForeignKey(
        "kms.OrgEncryptionKey",
        on_delete=models.CASCADE,
        related_name="membership_keys",
    )
    sealed_org_private_key = models.TextField(
        _("sealed org private key"),
        help_text=_(
            "Org X25519 private key sealed with the member's public key "
            "via crypto_box_seal. Unsealed client-side only."
        ),
    )

    def __str__(self):
        return f"{self.membership} / {self.org_encryption_key.key_id}"
