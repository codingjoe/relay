from django.db import models
from django.utils.translation import gettext_lazy as _


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

    class Meta:
        ordering = ("-modified_at", "-created_at")
        get_latest_by = "created_at"
        abstract = True
