from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from services.email.msa.models import OutgoingMessage, Transmission

from . import tasks


def enqueue_org_reputation_check(org_id):
    """Schedule a reputation check after the surrounding transaction commits."""
    transaction.on_commit(lambda: tasks.check_org_reputation.enqueue(org_id=org_id))


@receiver(post_save, sender=Transmission)
def check_reputation_on_hard_bounce(sender, instance, **kwargs):
    """Queue a reputation check when a transmission hard bounces."""
    if (
        instance.status == Transmission.Status.BOUNCED
        and instance.code
        and instance.code >= 500
    ):
        enqueue_org_reputation_check(instance.message.org_id)


@receiver(post_save, sender=OutgoingMessage)
def check_reputation_on_held_message(sender, instance, **kwargs):
    """Queue a reputation check when an outgoing message is held as spam."""
    if instance.status == OutgoingMessage.Status.HELD:
        enqueue_org_reputation_check(instance.org_id)
