"""python-social-auth pipeline extensions."""

from django.db import transaction

from .models import Membership, Organization


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
