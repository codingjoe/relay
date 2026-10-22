from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import Membership

from . import tasks
from .models import OnboardingCampaign


@receiver(post_save, sender=Membership)
def start_onboarding_campaign(sender, instance, created, **kwargs):
    """Give an organization its sequence when its first admin joins."""
    if created and not kwargs.get("raw") and instance.role == Membership.Role.ADMIN:
        campaign, campaign_created = OnboardingCampaign.objects.get_or_create(
            org=instance.org
        )
        if campaign_created:
            transaction.on_commit(
                lambda: tasks.send_onboarding_email.enqueue(campaign_pk=campaign.pk)
            )
