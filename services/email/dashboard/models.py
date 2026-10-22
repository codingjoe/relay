import datetime

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.models import TimeStamped
from accounts.models import Organization

# Reminders land at 09:00 in the project timezone, after the morning stand-up
# and before the day's first deep work. `days` counts from today, and a weekend
# landing moves to the next Monday.
SEND_HOUR = 9


def next_send_time(days: int) -> datetime.datetime:
    """Return the next weekday morning that is `days` away."""
    moment = (timezone.localtime() + datetime.timedelta(days=days)).replace(
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

    org = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="onboarding_campaign",
        help_text=_("Organization the sequence walks through onboarding."),
    )
    stage = models.TextField(
        _("stage"),
        choices=Stage,
        default=Stage.WELCOME,
        help_text=_("Email the sequence sends next."),
    )
    next_send_at = models.DateTimeField(
        _("next send"),
        null=True,
        blank=True,
        default=timezone.now,
        db_index=True,
        help_text=_("When the next email is due. Empty once the sequence ends."),
    )
    completed_at = models.DateTimeField(
        _("completed"),
        null=True,
        blank=True,
        help_text=_("When onboarding finished, which stops the sequence."),
    )

    def __str__(self):
        return f"{self.org} / {self.get_stage_display()}"

    def mark_email_sent(self):
        """Schedule the next email, or end the sequence after the last one."""
        stage_class = type(self).Stage
        match self.stage:
            case stage_class.WELCOME:
                self.stage = stage_class.FIRST_REMINDER
                self.next_send_at = next_send_time(days=1)
            case stage_class.FIRST_REMINDER:
                self.stage = stage_class.SECOND_REMINDER
                self.next_send_at = next_send_time(days=2)
            case stage_class.SECOND_REMINDER:
                self.stage = stage_class.LAST_REMINDER
                self.next_send_at = next_send_time(days=4)
            case _:
                self.next_send_at = None
        self.save(update_fields=["stage", "next_send_at", "modified_at"])

    def complete(self):
        """Stop the sequence because the organization finished onboarding."""
        self.completed_at = timezone.now()
        self.next_send_at = None
        self.save(update_fields=["completed_at", "next_send_at", "modified_at"])
