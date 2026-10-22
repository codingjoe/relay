import typing
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, ngettext
from django.utils.translation import gettext_lazy as _
from django_letter.notifications import Notification

from accounts.models import Organization
from services.email.msa.models import OutgoingMessage

from . import chart
from .billing import month_cost
from .charts import build_volume_chart, sent_per_day
from .evaluation import ReputationSummary, build_reputation_stats

weekly_digest_notification = Notification(
    "weekly-digest",
    _("Weekly digest"),
    _(
        "A weekly summary of your sending volume and sender reputation. "
        "Sent by default."
    ),
)


def build_org_digest(org: Organization) -> dict[str, typing.Any]:
    """Return the numbers the mail shows for one organization."""
    volume = build_volume_chart(org)
    window_days = max(settings.RELAY_REPUTATION_WINDOW_DAYS, 1)
    start = timezone.localdate() - timedelta(days=window_days - 1)
    window_counts = sent_per_day(org, start)
    return build_digest_context(
        org,
        stats=build_reputation_stats(org),
        month_messages=volume["this_month_total"],
        daily_counts=[
            window_counts.get(start + timedelta(days=offset), 0)
            for offset in range(window_days)
        ],
        recipients=count_window_recipients(org, window_days),
    )


def count_window_recipients(org: Organization, window_days: int) -> int:
    """Return how many distinct addresses the window's messages were addressed to."""
    # Keep the window and the filters in step with `compute_org_reputation`.
    return (
        OutgoingMessage.objects.filter(
            org=org,
            created_at__gte=timezone.now() - timedelta(days=window_days),
        )
        .exclude(status=OutgoingMessage.Status.SANDBOXED)
        .exclude(is_sandbox=True)
        .values("rcpt_to")
        .distinct()
        .count()
    )


def digest_illustration(stats: ReputationSummary) -> tuple[str, str]:
    """Return the light and dark illustrations for one window, none on a breach."""
    match stats:
        case _ if stats["hard_bounce_over_limit"] or stats["complaint_over_limit"]:
            return "", ""
        case _:
            return (
                "img/illustrations/all-the-data-light.svg",
                "img/illustrations/all-the-data-dark.svg",
            )


def message_interval(daily_average: int) -> str:
    """Return how often a message left the building, in words."""
    # The minute arm starts at 90 seconds, so only the seconds arm has a singular.
    interval = timedelta(days=1) / daily_average if daily_average else timedelta()
    match seconds := int(interval.total_seconds()):
        case 0 if daily_average:  # the interval truncates below one second
            return gettext("more than one a second")
        case 0:
            return ""
        case _ if interval < timedelta(seconds=90):
            return ngettext(
                "one every second", "one every %(count)d seconds", seconds
            ) % {"count": seconds}
        case _ if interval < timedelta(minutes=90):
            return gettext("one every %(count)d minutes") % {
                "count": round(interval / timedelta(minutes=1))
            }
        case _:
            return gettext("one every %(count)d hours") % {
                "count": round(interval / timedelta(hours=1))
            }


def build_digest_context(
    org: Organization,
    stats: ReputationSummary,
    month_messages: int,
    daily_counts: list[int],
    recipients: int,
) -> dict[str, typing.Any]:
    """Return the rates, their limits, and the month so far for one organization."""
    window_days = max(settings.RELAY_REPUTATION_WINDOW_DAYS, 1)
    free_monthly_messages = settings.RELAY_FREE_MONTHLY_MESSAGES
    illustration = digest_illustration(stats)
    return {
        "stats": stats,
        "organization": org.slug,
        "window_phrase": ngettext("last %d day", "last %d days", window_days)
        % window_days,
        "daily_average": round(stats["total_sent"] / window_days),
        "illustration_light": illustration[0],
        "illustration_dark": illustration[1],
        "message_interval": message_interval(round(stats["total_sent"] / window_days)),
        "bounce_threshold": settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD,
        "complaint_threshold": settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD,
        "month_messages": month_messages,
        "recipients": recipients,
        "week_chart": (
            # The chart builder emits its own SVG.
            mark_safe(chart.week(daily_counts))  # noqa: S308
            if any(daily_counts)
            else ""
        ),
        "cost": month_cost(month_messages),
        "free_monthly_messages": free_monthly_messages,
        "dashboard_path": reverse("monitoring:overview", kwargs={"org_slug": org.slug}),
    }


def sample_org_digest() -> dict[str, typing.Any]:
    """Return a busy window for the mail preview."""
    return build_digest_context(
        Organization(slug="acme"),
        stats=ReputationSummary(
            total_sent=12480,
            hard_bounces=0,
            soft_bounces=17,
            complaints=0,
            hard_bounce_rate=0.0,
            complaint_rate=0.0,
            hard_bounce_over_limit=False,
            complaint_over_limit=False,
        ),
        month_messages=42100,
        daily_counts=[980, 1420, 2310, 1750, 2640, 1880, 1500],
        recipients=214,
    )
