from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class TimeStamped(models.Model):
    modified_at = models.DateTimeField(
        _("modified"),
        default=timezone.now,
        editable=False,
        db_index=True,
    )
    created_at = models.DateTimeField(
        _("created"),
        default=timezone.now,
        editable=False,
        db_index=True,
    )

    class Meta:
        ordering = ("-modified_at", "-created_at")
        get_latest_by = "created_at"
        abstract = True

    def save(self, *args, **kwargs):
        self.modified_at = timezone.now()
        if update_fields := kwargs.get("update_fields"):
            kwargs["update_fields"] = {*update_fields, "modified_at"}
        super().save(*args, **kwargs)
