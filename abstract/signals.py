from django.db import close_old_connections
from django.dispatch import receiver
from django.tasks import signals


@receiver([signals.task_started, signals.task_finished])
def close_task_database_connection(sender, task_result, **kwargs):
    """Return the task worker thread's pooled database connection to the pool."""
    close_old_connections()
