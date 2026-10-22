import datetime

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Organization

# Reminders land at 09:00 in the project timezone, after the morning stand-up
# and before the day's first deep work. A weekend landing moves to Monday.
SEND_HOUR = 9


def send_time(
    start: datetime.datetime, offset: datetime.timedelta
) -> datetime.datetime:
    """Return the 09:00 weekday that is `offset` after `start`."""
    if not offset:
        return start
    moment = (timezone.localtime(start) + offset).replace(
        hour=SEND_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )
    while moment.weekday() >= 5:
        moment += datetime.timedelta(days=1)
    return moment


class OnboardingMail(TimeStamped):
    """Record one onboarding mail that went out to an organization."""

    class Stage(models.TextChoices):
        WELCOME = "welcome", _("welcome")
        FIRST_REMINDER = "first-reminder", _("first reminder")
        SECOND_REMINDER = "second-reminder", _("second reminder")
        LAST_REMINDER = "last-reminder", _("last reminder")

    # Delay after sign-up. Each mail is due on its own day, so the schedule
    # needs no progress state beyond the row that records a sent mail.
    SEND_OFFSETS = {
        Stage.WELCOME: datetime.timedelta(0),
        Stage.FIRST_REMINDER: datetime.timedelta(days=2),
        Stage.SECOND_REMINDER: datetime.timedelta(days=6),
        Stage.LAST_REMINDER: datetime.timedelta(days=13),
    }

    org = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="onboarding_mails",
        help_text=_("Organization the mail went to."),
    )
    stage = models.TextField(
        _("stage"),
        choices=Stage,
        help_text=_("Which mail of the sequence went out."),
    )

    class Meta(TimeStamped.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["org", "stage"],
                name="unique_onboarding_mail_per_org",
            ),
        ]

    def __str__(self):
        return f"{self.org} / {self.get_stage_display()}"
