from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, ngettext

from accounts.models import Membership, Organization
from services.email.msa.models import OutgoingMessage, SuppressionEntry

from .billing import month_cost
from .charts import build_volume_chart, sent_per_day
from .evaluation import ReputationSummary, build_reputation_stats


def build_org_digest(org: Organization) -> dict[str, Any]:
    """
    Return the numbers the mail shows for one organization.

    The rolling window matches the one the suspension check uses, while the
    dashboard cards read the day-aligned chart, so a card can differ from the
    mail by up to a day of traffic.
    """
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
    """Return how many distinct addresses the window's messages went to."""
    return (
        OutgoingMessage.objects.filter(
            org=org,
            created_at__gte=timezone.now() - timedelta(days=window_days),
        )
        .exclude(status=OutgoingMessage.Status.SANDBOXED)
        .values("rcpt_to")
        .distinct()
        .count()
    )


def chart_url(org: Organization, name: str, **query) -> str:
    """Return the path of one digest chart, with its numbers in the query."""
    path = reverse(f"monitoring:{name}", kwargs={"org_slug": org.slug})
    return f"{path}?{urlencode(query)}"


def digest_illustration(stats: ReputationSummary) -> tuple[str, str]:
    """
    Return the pair of illustrations the mail shows for one window.

    The pairs are light and dark, so a client that reports a dark scheme gets
    the drawing that belongs on it. A breach shows none, and stays plain.
    """
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
    match seconds := 86400 // daily_average if daily_average else 0:
        case 0:
            return ""
        case _ if seconds < 90:
            return ngettext(
                "one every second", "one every %(count)d seconds", seconds
            ) % {"count": seconds}
        case _ if seconds < 5400:
            return gettext("one every %(count)d minutes") % {
                "count": round(seconds / 60)
            }
        case _:
            return gettext("one every %(count)d hours") % {
                "count": round(seconds / 3600)
            }


def build_digest_context(
    org: Organization,
    stats: ReputationSummary,
    month_messages: int,
    daily_counts: list[int],
    recipients: int,
) -> dict[str, Any]:
    """
    Return the window rates, their limits, the month so far, and its cost.

    The organization the mail names, the window phrase it reports, and the
    chart it links all come from the same context.
    """
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
        "week_chart_url": (
            chart_url(
                org,
                "digest-week",
                counts=",".join(str(count) for count in daily_counts),
            )
            if any(daily_counts)
            else ""
        ),
        "cost": month_cost(month_messages),
        "free_monthly_messages": free_monthly_messages,
        "dashboard_path": reverse("monitoring:overview", kwargs={"org_slug": org.slug}),
    }


def sample_org_digest() -> dict[str, Any]:
    """
    Return a clean, busy window for the mail preview.

    The preview renders for an organization that no database knows about.
    """
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


def iter_digest_members(org: Organization) -> Iterator[Membership]:
    """
    Yield the members of one organization that the digest reaches.

    A member with a deactivated account, no address, or a suppressed address
    is skipped.
    """
    for membership in (
        Membership.objects.filter(org=org, user__is_active=True)
        .exclude(user__email="")
        .select_related("user")
    ):
        if not SuppressionEntry.objects.is_suppressed(org, membership.user.email):
            yield membership
