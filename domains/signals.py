from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import Organization

from .models import Domain


@receiver(post_save, sender=Organization)
def create_managed_domain(sender, instance, created, **kwargs):
    """Create a relay-managed subdomain for a new organization."""
    if created and not kwargs.get("raw"):
        name = Domain.managed_domain_name(instance)
        Domain.objects.get_or_create(
            name=name,
            defaults={
                "org": instance,
                "is_managed": True,
                "verified_at": timezone.now(),
                "nameserver_status": Domain.Status.OK,
                "spf_status": Domain.Status.OK,
                "dkim_status": Domain.Status.OK,
                "dmarc_status": Domain.Status.OK,
            },
        )
