from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from services.email.msa.models import OutgoingMessage, Transmission
from services.email.mta.models import IncomingMessage, is_fbl_report

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
def check_reputation_on_incoming_message(sender, instance, created, **kwargs):
    """Store provider FBL reports sent to the FBL inbox and record relay
    reports for quarantined mail."""
    if created and is_fbl_report(instance.mail_from, instance.rcpt_to):
        report = FblReport.create_for_incoming(instance)
        transaction.on_commit(
            lambda: tasks.parse_fbl_report.enqueue(report_pk=str(report.pk))
        )
    elif instance.status == IncomingMessage.Status.QUARANTINED and "status" in (
        kwargs.get("update_fields") or ()
    ):
        FblReport.create_for_spam(instance)
