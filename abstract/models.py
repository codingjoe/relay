import datetime
import uuid

import sentry_sdk
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class FetchPeersManager(models.Manager):
    """Fetch lazily-missed fields in one batched query per field."""

    def get_queryset(self):
        return super().get_queryset().fetch_mode(models.FETCH_PEERS)


class TimeStamped(models.Model):
    modified_at = models.DateTimeField(
        _("modified"),
        auto_now=True,
        editable=False,
        db_index=True,
    )
    created_at = models.DateTimeField(
        _("created"),
        auto_now_add=True,
        editable=False,
        db_index=True,
    )

    objects = FetchPeersManager()

    class Meta:
        ordering = ("-modified_at", "-created_at")
        get_latest_by = "created_at"
        abstract = True

    def save(self, *args, update_fields=None, **kwargs):
        """Persist `modified_at` on partial saves, so conditional GETs revalidate."""
        if update_fields is not None:
            update_fields = {*update_fields, "modified_at"}
        return super().save(*args, update_fields=update_fields, **kwargs)


class Timing(TimeStamped):
    """
    Time a block of code and label it for the message timeline.

    Use as a context manager to stamp the start and end of a block, persist
    the timing on exit, and trace it as a Sentry span. A start stamped before
    entering is kept. Concrete timings implement `label`.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    started_at = models.DateTimeField(
        _("started"),
        db_index=True,
        help_text=_("When the timing started."),
    )
    finished_at = models.DateTimeField(
        _("finished"),
        db_index=True,
        help_text=_("When the timing finished."),
    )

    class Meta(TimeStamped.Meta):
        ordering = ["started_at", "created_at"]
        abstract = True

    def __enter__(self):
        if self.started_at is None:
            self.started_at = timezone.now()
        op = str(self._meta.verbose_name)
        if sentry_sdk.get_current_span() is None:
            # Transaction mode drops parentless spans, so start a trace instead.
            self._span = sentry_sdk.start_transaction(op=op, name=op)
        else:
            self._span = sentry_sdk.start_span(op=op, name=op)
        self._span.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            self.finished_at = timezone.now()
            self.save(force_insert=True)
        finally:
            self.finish_span(exc_type, exc_value, traceback)

    def finish_span(self, exc_type, exc_value, traceback):
        """Finish the Sentry span, recording the model's duration."""
        label = self.label
        if label:
            # Transactions read `name`, child spans read `description`.
            self._span.name = label
            self._span.description = label
        if self.finished_at is not None:
            self._span.set_data("timing.duration_secs", self.duration.total_seconds())
        self._span.__exit__(exc_type, exc_value, traceback)

    @property
    def duration(self) -> datetime.timedelta:
        """Return the elapsed time the timing recorded."""
        return self.finished_at - self.started_at

    @property
    def label(self) -> str:
        """Return the display name of this timing."""
        raise NotImplementedError

    @property
    def event(self) -> dict:
        """Return the profile chart event payload for this timing."""
        raise NotImplementedError
