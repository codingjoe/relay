from contextlib import contextmanager
from functools import wraps

from django.core.signals import request_finished, request_started


@contextmanager
def request_scope():
    """
    Emit `request_started` and `request_finished` around a non-HTTP request.

    The request lifecycle is not limited to HTTP: a DNS query or an SMTP
    submission is a request too. Emitting the signals lets Django's built-in
    receivers run for every request unit, so pooled database connections
    return to the pool and the query log resets, exactly as for HTTP.
    """
    request_started.send(sender=request_scope)
    try:
        yield
    finally:
        request_finished.send(sender=request_scope)


def request_scoped(func):
    """Emit `request_started` and `request_finished` around a non-HTTP request."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with request_scope():
            return func(*args, **kwargs)

    return wrapper
