from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Membership

from . import tasks


@receiver(post_save, sender=Membership)
def start_onboarding_emails(sender, instance, created, **kwargs):
    """Schedule the sequence when an organization gets its first admin."""
    if (
        created
        and not kwargs.get("raw")
        and instance.role == Membership.Role.ADMIN
        and not Membership.objects.filter(
            org_id=instance.org_id, role=Membership.Role.ADMIN
        )
        .exclude(pk=instance.pk)
        .exists()
    ):
        transaction.on_commit(
            lambda: tasks.schedule_onboarding_emails.enqueue(org_pk=instance.org_id)
        )
