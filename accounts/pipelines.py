"""python-social-auth pipeline extensions."""

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from social_core.exceptions import AuthException

from .models import Membership, Organization


class VerifiedEmailRequiredError(AuthException):
    """Raised when a signup carries no verified email address."""


def get_verified_email(response, profile_email=""):
    """
    Return the verified email GitHub exposes for the account.

    GitHub hides the profile email of private accounts, so the emails endpoint
    is the source of truth and the profile email the fallback.
    """
    emails = response.get("emails")
    if emails is None:
        return profile_email
    verified = [
        entry
        for entry in emails
        if isinstance(entry, dict) and entry.get("verified") and entry.get("email")
    ]
    primary = [entry for entry in verified if entry.get("primary")]
    preferred = primary or verified
    return preferred[0]["email"] if preferred else ""


def attach_verified_email(backend, details, response, user=None, *args, **kwargs):
    """
    Store the email GitHub exposes for the account.

    A signup without a verified address is refused. An existing account keeps
    the address it already has.
    """
    email = get_verified_email(response, details.get("email", ""))
    if user is None:
        if not email:
            raise VerifiedEmailRequiredError(
                backend,
                _(
                    "Add a verified email address to your GitHub account, "
                    "then sign in again."
                ),
            )
        outcome = {"details": {**details, "email": email}}
    else:
        if email and not user.email:
            user.email = email
            user.save(update_fields=["email"])
        outcome = {}
    return outcome


@transaction.atomic
def create_default_organization(backend, user, response, is_new=False, *args, **kwargs):
    """Create a personal organization with admin membership for new users."""
    if is_new:
        org = Organization.objects.create(slug=user.username)
        Membership.objects.create(
            org=org,
            user=user,
            role=Membership.Role.ADMIN,
        )
