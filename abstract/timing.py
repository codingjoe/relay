"""Timing utilities."""

import datetime
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from django.utils import timezone


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
