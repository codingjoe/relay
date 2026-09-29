from collections.abc import Iterator
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils.translation import ngettext

from accounts.models import Membership, Organization
from services.email.msa.models import SuppressionEntry

from .billing import month_cost, overage_price
from .charts import build_volume_chart
from .evaluation import ReputationSummary, build_reputation_stats


def build_org_digest(org: Organization) -> dict[str, Any]:
    """
    Return the numbers the mail shows for one organization.

    The rolling window matches the one the suspension check uses, while the
    dashboard cards read the day-aligned chart, so a card can differ from the
    mail by up to a day of traffic.
    """
    volume = build_volume_chart(org)
    return build_digest_context(
        org,
        stats=build_reputation_stats(org),
        month_messages=volume["this_month_total"],
        month_last_messages=volume["rows"][-1]["last_month"] or 0,
    )


def share(value: float, total: float) -> float:
    """Return how much of a total a value fills, in per cent."""
    return min(value / total, 1) * 100 if total else 0.0


def digest_illustration(stats: ReputationSummary) -> str:
    """Return the illustration the mail shows for one window."""
    match stats:
        case {"total_sent": 0}:
            return "img/illustrations/empty-mailbox-light.svg"
        case {"hard_bounce_rate": 0.0, "complaint_rate": 0.0}:
            return "img/illustrations/protection-enabled-light.svg"
        case _ if stats["hard_bounce_over_limit"] or stats["complaint_over_limit"]:
            return ""
        case _:
            return "img/illustrations/connected-light.svg"


def build_digest_context(
    org: Organization,
    stats: ReputationSummary,
    month_messages: int,
    month_last_messages: int,
) -> dict[str, Any]:
    """
    Return the window rates, their limits, the month so far, and its cost.

    The organization the mail names and the window phrase it reports come
    from the same context, and the bars it draws are shares of a limit or of
    the largest month on show.
    """
    window_days = max(settings.RELAY_REPUTATION_WINDOW_DAYS, 1)
    free_monthly_messages = settings.RELAY_FREE_MONTHLY_MESSAGES
    volume_scale = max(month_messages, month_last_messages, free_monthly_messages, 1)
    return {
        "stats": stats,
        "organization": org.slug,
        "window_phrase": ngettext("last %d day", "last %d days", window_days)
        % window_days,
        "daily_average": round(stats["total_sent"] / window_days),
        "illustration": digest_illustration(stats),
        "bounce_threshold": settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD,
        "complaint_threshold": settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD,
        "bounce_limit_share": share(
            stats["hard_bounce_rate"],
            settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD,
        ),
        "complaint_limit_share": share(
            stats["complaint_rate"],
            settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD,
        ),
        "month_messages": month_messages,
        "month_last_messages": month_last_messages,
        "month_bar_share": share(month_messages, volume_scale),
        "last_month_bar_share": share(month_last_messages, volume_scale),
        "free_tier_bar_share": share(free_monthly_messages, volume_scale),
        "cost": month_cost(month_messages),
        "free_monthly_messages": free_monthly_messages,
        "overage_price": overage_price(),
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
        month_last_messages=38400,
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
