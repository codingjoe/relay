import datetime
import logging
from enum import StrEnum

from django.tasks import TaskContext
from django.utils import timezone

logger = logging.getLogger(__name__)

# A failed scan is a problem on our side and never a reason to lose a message,
# so scans retry until they succeed. One run ramps up and then hands over to a
# fresh run that probes once an hour.
SPAM_SCAN_RETRY_RENEWAL_ATTEMPT = 9
SPAM_SCAN_RETRY_BASE_DELAY = datetime.timedelta(seconds=1)
SPAM_SCAN_RETRY_RENEWAL_DELAY = datetime.timedelta(hours=1)


class UnscannableReason(StrEnum):
    """Why no attempt can scan a message."""

    MESSAGE_GONE = "message gone"
    BODY_GONE = "stored body gone"


class UnscannableMessageError(Exception):
    """The message or its stored body is gone, so no attempt can scan it."""


UNSCANNABLE_MESSAGE_PATH = (
    f"{UnscannableMessageError.__module__}.{UnscannableMessageError.__qualname__}"
)


def retry_spam_scan(context: TaskContext) -> datetime.timedelta | None:
    """Return the delay before the next attempt, or None to stop retrying."""
    task_result = context.task_result
    errors = task_result.errors
    if errors and errors[-1].exception_class_path == UNSCANNABLE_MESSAGE_PATH:
        logger.error(
            "Giving up on spam scan %s, the message is unscannable", task_result.id
        )
        return None
    is_renewal = bool(task_result.kwargs.get("is_renewal"))
    if not is_renewal and context.attempt < SPAM_SCAN_RETRY_RENEWAL_ATTEMPT:
        return SPAM_SCAN_RETRY_BASE_DELAY * 2 ** (context.attempt - 1)
    task_result.task.using(
        run_after=timezone.now() + SPAM_SCAN_RETRY_RENEWAL_DELAY
    ).enqueue(*task_result.args, **{**task_result.kwargs, "is_renewal": True})
    return None
