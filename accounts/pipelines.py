"""python-social-auth pipeline extensions."""

from .models import Membership, Organization


def create_default_organization(backend, user, response, is_new=False, *args, **kwargs):
    """Create a personal organization with admin membership for new users."""
    if not is_new:
        return
    org = Organization.objects.create(name=user.username)
    Membership.objects.create(
        organization=org,
        user=user,
        role=Membership.Role.ADMIN,
    )
