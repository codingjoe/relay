"""python-social-auth pipeline extensions."""

from domains.models import Credential


def create_default_credential(backend, user, response, is_new=False, *args, **kwargs):
    """Create a default SMTP credential for newly registered users."""
    if is_new:
        Credential.objects.create(owner=user, type=Credential.Type.SMTP, name="default")
