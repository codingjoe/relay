from contextlib import contextmanager
from functools import wraps

from django.core.signals import request_finished, request_started


@contextmanager
def request_scope(func):
    """
    Emit `request_started` and `request_finished` around a non-HTTP request.

    Django's built-in receivers run for the request unit, so pooled database
    connections return to the pool and the query log resets as for HTTP.
    """
    request_started.send(sender=func)
    try:
        yield
    finally:
        request_finished.send(sender=func)


def request_scoped(func):
    """Emit `request_started` and `request_finished` around a non-HTTP request."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with request_scope(func):
            return func(*args, **kwargs)

    return wrapper
