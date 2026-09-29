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
    return build_digest_context(
        org,
        stats=build_reputation_stats(org),
        month_messages=build_volume_chart(org)["this_month_total"],
    )


def build_digest_context(
    org: Organization, stats: ReputationSummary, month_messages: int
) -> dict[str, Any]:
    """
    Return the window rates, their limits, the month so far, and the
    organization and window phrase the mail names.
    """
    window_days = max(settings.RELAY_REPUTATION_WINDOW_DAYS, 1)
    return {
        "stats": stats,
        "organization": org.slug,
        "window_phrase": ngettext("last %d day", "last %d days", window_days)
        % window_days,
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
    )


def iter_digest_members(org: Organization) -> Iterator[Membership]:
    """
    Yield the members of one organization that the digest reaches.

    A member with a deactivated account, no address, an opt-out for this
    organization, or a suppressed address is skipped.
    """
    for membership in (
        Membership.objects.filter(org=org, user__is_active=True)
        .exclude(user__email="")
        .exclude(user__digest_opt_outs__org=org)
        .select_related("user")
    ):
        if not SuppressionEntry.objects.is_suppressed(org, membership.user.email):
            yield membership
