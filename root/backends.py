from django.tasks.backends.immediate import ImmediateBackend
from threadmill.backends.base import RetryTask


class ImmediateRetryBackend(ImmediateBackend):
    """ImmediateBackend that accepts Threadmill's retry parameter.

    Runs tasks synchronously without a worker process. The retry callback
    is never called — tasks that raise exceptions are marked FAILED and the
    exception is stored in the result. Used in tests and local development.
    """

    task_class = RetryTask
