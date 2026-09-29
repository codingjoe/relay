from typing import Any

from django.conf import settings
from django.urls import reverse

from accounts.models import Organization

from .billing import month_cost, overage_price
from .charts import build_volume_chart
from .evaluation import ReputationSummary, build_reputation_stats


def build_org_digest(org: Organization) -> dict[str, Any]:
    """
    Return the numbers the mail shows for one organization.

    The monitoring dashboard shows the same numbers, so the mail and the
    dashboard cannot disagree.
    """
    return build_digest_context(
        org,
        stats=build_reputation_stats(org),
        month_messages=build_volume_chart(org)["this_month_total"],
    )


def build_digest_context(
    org: Organization, stats: ReputationSummary, month_messages: int
) -> dict[str, Any]:
    """Return the window rates, their limits, and the month so far."""
    window_days = max(settings.RELAY_REPUTATION_WINDOW_DAYS, 1)
    return {
        "stats": stats,
        "window_days": window_days,
        "messages_per_day": round(stats["total_sent"] / window_days, 1),
        "bounce_threshold": settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD,
        "complaint_threshold": settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD,
        "month_messages": month_messages,
        "cost": month_cost(month_messages),
        "free_monthly_messages": settings.RELAY_FREE_MONTHLY_MESSAGES,
        "overage_price": overage_price(),
        "dashboard_path": reverse("monitoring:overview", kwargs={"org_slug": org.slug}),
    }


def sample_org_digest() -> dict[str, Any]:
    """
    Return a clean, busy week for the mail preview.

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
    )
