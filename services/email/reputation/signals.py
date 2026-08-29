from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from services.email.msa.models import OutgoingMessage, Transmission
from services.email.mta.models import IncomingMessage
from services.email.mta.signals import fbl_report_received

from . import tasks
from .models import FblReport


@receiver(post_save, sender=Transmission)
def check_reputation_on_hard_bounce(sender, instance, **kwargs):
    """Enqueue an org evaluation after commit when a transmission bounces
    with SMTP 5xx."""
    if (
        instance.status == Transmission.Status.BOUNCED
        and instance.code
        and instance.code >= 500
    ):
        org_id = instance.message.org_id
        transaction.on_commit(lambda: tasks.check_org_reputation.enqueue(org_id=org_id))


@receiver(post_save, sender=OutgoingMessage)
def check_reputation_on_held_message(sender, instance, **kwargs):
    """Record a relay FBL report and queue an org evaluation when
    Relay flags a submission as spam."""
    held_as_spam = instance.status == OutgoingMessage.Status.HELD and "status" in (
        kwargs.get("update_fields") or ()
    )
    if held_as_spam:
        FblReport.create_for_spam(instance)
        transaction.on_commit(
            lambda: tasks.check_org_reputation.enqueue(org_id=instance.org_id)
        )


@receiver(post_save, sender=IncomingMessage)
def check_reputation_on_incoming_message(sender, instance, **kwargs):
    """Record a relay FBL report when the MTA quarantines incoming mail.

    The report is visibility-only. Quarantined incoming mail does not
    affect the organization's sending reputation, so no evaluation
    follows.
    """
    if instance.status == IncomingMessage.Status.QUARANTINED and "status" in (
        kwargs.get("update_fields") or ()
    ):
        FblReport.create_for_spam(instance)


@receiver(fbl_report_received)
def create_provider_fbl_report(sender, message, **kwargs):
    """Record a provider FBL report and queue its parsing after commit."""
    report = FblReport.create_for_incoming(message)
    transaction.on_commit(
        lambda: tasks.parse_fbl_report.enqueue(report_pk=str(report.pk))
    )
