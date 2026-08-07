from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from accounts.models import Organization

from .models import Domain


@receiver(post_save, sender=Organization)
def synchronize_managed_domain(sender, instance, created, **kwargs):
    """Keep an organization's managed domain synchronized with its slug."""
    update_fields = kwargs.get("update_fields")
    if not kwargs.get("raw") and (
        created or update_fields is None or "slug" in update_fields
    ):
        verified_at = timezone.now()
        managed_domain_name = f"{instance.slug}.{settings.RELAY_MANAGED_SENDER_DOMAIN}"
        try:
            domain = Domain.objects.get(org=instance, is_managed=True)
        except Domain.DoesNotExist:
            domain = Domain(
                name=managed_domain_name,
                org=instance,
                is_managed=True,
                verified_at=verified_at,
                dns_checked_at=verified_at,
                nameserver_status=Domain.Status.OK,
                spf_status=Domain.Status.OK,
                dkim_status=Domain.Status.OK,
                dmarc_status=Domain.Status.OK,
                mta_sts_status=Domain.Status.OK,
                tls_rpt_status=Domain.Status.OK,
            )
            domain.full_clean()
            domain.save(force_insert=True)
        else:
            if domain.name != managed_domain_name:
                domain.name = managed_domain_name
                domain.full_clean()
                domain.save(update_fields=["name"])
