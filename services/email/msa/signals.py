from django.db import transaction
from django.dispatch import receiver

from services.email.mta.signals import bounce_report_received

from . import tasks


@receiver(bounce_report_received)
def queue_parse_bounce_report(sender, message, **kwargs):
    """Queue the parse task for a received bounce DSN after commit.

    The task matches the original outgoing message and records the
    post-acceptance bounce or delay.
    """
    transaction.on_commit(
        lambda: tasks.parse_bounce_report.enqueue(message_pk=str(message.id))
    )
