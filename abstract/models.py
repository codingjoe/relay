import uuid

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


class Timing(TimeStamped):
    """
    Time a block of code and label it for the message timeline.

    Use as a context manager to stamp the start and end of a block and
    persist the timing on exit. Concrete timings override the label.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid7,
        editable=False,
    )
    started_at = models.DateTimeField(
        _("started"),
        help_text=_("When the timing started."),
    )
    finished_at = models.DateTimeField(
        _("finished"),
        help_text=_("When the timing finished."),
    )

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
