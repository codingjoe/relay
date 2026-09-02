from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from domains.models import Domain

from .models import Webhook

fbl_report_received = Signal()  # senders provide a `message` kwarg

report_received = Signal()  # senders provide the incoming report email metadata


@receiver(post_save, sender=Domain)
def synchronize_webhook_address_patterns(sender, instance, created, **kwargs):
    """Update webhook address patterns after a receiving domain is renamed."""
    update_fields = kwargs.get("update_fields")
    if (
        not created
        and not kwargs.get("raw")
        and (update_fields is None or "name" in update_fields)
    ):
        for webhook in Webhook.objects.filter(domain=instance):
            pattern_prefix, separator, _ = webhook.address_pattern.rpartition("@")
            if separator:
                address_pattern = f"{pattern_prefix}@{instance.name}"
                if webhook.address_pattern != address_pattern:
                    webhook.address_pattern = address_pattern
                    webhook.save(update_fields=["address_pattern"])
