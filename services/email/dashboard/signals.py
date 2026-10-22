from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Membership

from . import tasks
from .models import OnboardingMail


@receiver(post_save, sender=Membership)
def send_onboarding_welcome(sender, instance, created, **kwargs):
    """Send the welcome as soon as the first admin joins, rather than at the next cron."""
    if created and not kwargs.get("raw") and instance.role == Membership.Role.ADMIN:
        transaction.on_commit(
            lambda: tasks.send_onboarding_email.enqueue(
                org_pk=instance.org_id,
                stage=OnboardingMail.Stage.WELCOME,
            )
        )
