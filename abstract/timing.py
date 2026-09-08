"""Timing utilities."""

import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from django.utils import timezone

from abstract.models import TimeStamped


class Timing(TimeStamped):
    """
    Time a block of code and label it for the message timeline.

    Use as a context manager to stamp the start and end of a block and
    persist the timing on exit. Concrete timings implement the fields and
    override the label.
    """

    class Meta:
        abstract = True

    def __enter__(self):
        """Stamp the start of the timed block."""
        self.started_at = timezone.now()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """Stamp the end of the timed block and persist the timing."""
        self.finished_at = timezone.now()
        self.save(force_insert=True)

    @property
    def label(self) -> str:
        """Return the display name of this timing."""
        return str(self._meta.verbose_name)


@dataclass(slots=True)
class Interval:
    """Store the wall-clock start and end of a measured block."""

    started_at: datetime.datetime
    finished_at: datetime.datetime | None = None

    @property
    def duration(self) -> datetime.timedelta | None:
        """Return the time between start and finish, or None while unfinished."""
        if self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@contextmanager
def measure() -> Iterator[Interval]:
    """
    Measure the wall-clock time of the wrapped block.

    Yield an interval whose `started_at` is set on entry and whose
    `finished_at` is set on exit, including when the block raises.
    """
    interval = Interval(started_at=timezone.now())
    try:
        yield interval
    finally:
        interval.finished_at = timezone.now()
