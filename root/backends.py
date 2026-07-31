from django.tasks.backends.immediate import ImmediateBackend
from threadmill.backends.base import RetryTask


class ImmediateRetryBackend(ImmediateBackend):
    task_class = RetryTask
