import datetime

from django.db import models
from django.db.models.functions import Now
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Organization

# Reminders land at 09:00 in the project timezone, after the morning stand-up
# and before the day's first deep work. A weekend landing moves to Monday.
SEND_HOUR = 9


def send_time(start: datetime.datetime, days: int) -> datetime.datetime:
    """Return the 09:00 weekday that is `days` after `start`."""
    if not days:
        return start
    moment = (timezone.localtime(start) + datetime.timedelta(days=days)).replace(
        hour=SEND_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    while moment.weekday() >= 5:
        moment += datetime.timedelta(days=1)
    return moment


class OnboardingCampaign(TimeStamped):
    """Walk an organization's admins through the first sending steps."""

    class Stage(models.TextChoices):
        WELCOME = "welcome", _("welcome")
        FIRST_REMINDER = "first-reminder", _("first reminder")
        SECOND_REMINDER = "second-reminder", _("second reminder")
        LAST_REMINDER = "last-reminder", _("last reminder")

    SEQUENCE = (
        Stage.WELCOME,
        Stage.FIRST_REMINDER,
        Stage.SECOND_REMINDER,
        Stage.LAST_REMINDER,
    )
    # Days after the campaign starts. The stage and the due time both follow
    # from this tuple and `sent_count`, so no second state can drift.
    SEND_OFFSETS = (0, 2, 6, 13)

    org = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="onboarding_campaign",
        help_text=_("Organization the sequence walks through onboarding."),
    )
    sent_count = models.PositiveSmallIntegerField(
        _("sent"),
        default=0,
        db_index=True,
        help_text=_("How many emails of the sequence have gone out."),
    )

    def __str__(self):
        return f"{self.org} / {self.stage.label if self.stage else _('done')}"

    @property
    def stage(self):
        """Return the email the sequence sends next, or `None` once it ran out."""
        try:
            return type(self).SEQUENCE[self.sent_count]
        except IndexError:
            return None

    @property
    def next_send_at(self):
        """Return when the next email is due, or `None` once it ran out."""
        if self.sent_count >= len(type(self).SEQUENCE):
            return None
        return send_time(self.created_at, type(self).SEND_OFFSETS[self.sent_count])

    def claim(self) -> bool:
        """Advance the sequence unless another worker already sent this email."""
        return bool(
            type(self)
            .objects.filter(pk=self.pk, sent_count=self.sent_count)
            .update(
                sent_count=models.F("sent_count") + 1,
                modified_at=Now(),
            )
        )
