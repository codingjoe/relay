from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import Organization

from .models import Domain


@receiver(post_save, sender=Organization)
def create_managed_domain(sender, instance, created, **kwargs):
    """Create a relay-managed subdomain for a new organization."""
    if not created or kwargs.get("raw"):
        return
    name = Domain.managed_domain_name(instance)
    Domain.objects.get_or_create(
        name=name,
        defaults={
            "org": instance,
            "verified_at": timezone.now(),
            "nameserver_status": Domain.Status.OK,
            "spf_status": Domain.Status.OK,
            "dkim_status": Domain.Status.OK,
            "dmarc_status": Domain.Status.OK,
        },
    )
