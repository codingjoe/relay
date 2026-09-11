import datetime

from django.tasks import TaskContext
from django.utils import timezone

# A failed scan is a problem on our side and never a reason to lose a message,
# so scans retry until they succeed. One run ramps up and then hands over to a
# fresh run that probes once an hour.
SPAM_SCAN_RETRY_RENEWAL_ATTEMPT = 9
SPAM_SCAN_RETRY_BASE_DELAY = datetime.timedelta(seconds=1)
SPAM_SCAN_RETRY_RENEWAL_DELAY = datetime.timedelta(hours=1)


def retry_spam_scan(context: TaskContext) -> datetime.timedelta | None:
    """Return the delay before the next attempt, or None to hand over to a renewal."""
    task_result = context.task_result
    is_renewal = bool(task_result.kwargs.get("is_renewal"))
    if not is_renewal and context.attempt < SPAM_SCAN_RETRY_RENEWAL_ATTEMPT:
        return SPAM_SCAN_RETRY_BASE_DELAY * 2 ** (context.attempt - 1)
    task_result.task.using(
        run_after=timezone.now() + SPAM_SCAN_RETRY_RENEWAL_DELAY
    ).enqueue(*task_result.args, **{**task_result.kwargs, "is_renewal": True})
    return None
