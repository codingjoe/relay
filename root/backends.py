from django.tasks.backends.immediate import ImmediateBackend
from threadmill.backends.base import RetryTask


class ImmediateRetryBackend(ImmediateBackend):
    task_class = RetryTask
    # Declaring defer support lets tests queue `run_after` tasks, which run now.
    supports_defer = True
