from django.tasks.backends.immediate import ImmediateBackend
from threadmill.backends.base import RetryTask


class ImmediateRetryBackend(ImmediateBackend):
    task_class = RetryTask
    # Immediate runs every task as it is queued, so a deferred task runs now.
    # Declaring support lets tests queue `run_after` tasks at all.
    supports_defer = True
