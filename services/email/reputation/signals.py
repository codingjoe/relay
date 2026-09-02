from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from services.email.msa.models import OutgoingMessage, Transmission
from services.email.mta.models import IncomingMessage
from services.email.mta.signals import fbl_report_received

from . import tasks


@receiver(post_save, sender=Transmission)
def check_reputation_on_hard_bounce(sender, instance, **kwargs):
    """
    Enqueue an org evaluation after commit when a transmission bounces.

    A bounced transmission is a permanent rejection; the message did not
    reach the recipient and counts against the sending reputation.
    """
    if instance.status == Transmission.Status.BOUNCED:
        org_id = instance.message.org_id
        transaction.on_commit(lambda: tasks.check_org_reputation.enqueue(org_id=org_id))


@receiver(post_save, sender=OutgoingMessage)
def check_reputation_on_held_message(sender, instance, **kwargs):
    """
    Queue the ingest task when Relay flags a submission as spam.

    The relay-generated report and the org evaluation are recorded in the
    task, after the message is fully ingested.
    """
    held_as_spam = instance.status == OutgoingMessage.Status.HELD and "status" in (
        kwargs.get("update_fields") or ()
    )
    if held_as_spam:
        transaction.on_commit(
            lambda: tasks.create_held_outgoing_fbl_report.enqueue(
                message_pk=str(instance.id),
                org_id=instance.org_id,
            )
        )


@receiver(post_save, sender=IncomingMessage)
def check_reputation_on_incoming_message(sender, instance, **kwargs):
    """
    Queue the ingest task when the MTA quarantines incoming mail.

    The report is visibility-only. Quarantined incoming mail does not
    affect the organization's sending reputation, so no evaluation
    follows.
    """
    if instance.status == IncomingMessage.Status.QUARANTINED and "status" in (
        kwargs.get("update_fields") or ()
    ):
        transaction.on_commit(
            lambda: tasks.create_quarantined_incoming_fbl_report.enqueue(
                message_pk=str(instance.id)
            )
        )


@receiver(fbl_report_received)
def create_provider_fbl_report(sender, message, **kwargs):
    """
    Queue the ingest task for a provider FBL report after commit.

    The task stores the report and queues its parsing.
    """
    transaction.on_commit(
        lambda: tasks.create_provider_fbl_report.enqueue(message_pk=str(message.id))
    )
