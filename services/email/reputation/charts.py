from datetime import timedelta

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext

from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage

from .models import FblReport

REPUTATION_CHART_COLORS = {
    "sent": "var(--color-chart-green)",
    "hard_bounced": "var(--color-chart-red)",
    "soft_bounced": "var(--color-chart-yellow)",
    "complained": "var(--color-chart-red)",
    "hard_bounce_rate": "var(--color-chart-red)",
    "complaint_rate": "var(--color-chart-orange)",
    "hard_bounce_limit": "var(--color-chart-gray)",
    "complaint_limit": "var(--color-chart-gray)",
    "this_month": "var(--color-chart-green)",
    "last_month": "var(--color-chart-gray)",
}


def sent_per_day(org, start):
    """Return the outgoing message count per day since `start`."""
    rows = (
        OutgoingMessage.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    return {row["day"]: row["count"] for row in rows}


def bounced_per_day(org, start):
    """Return the hard and soft bounce counts per day since `start`."""
    rows = (
        Transmission.objects.filter(
            message__org=org,
            message__created_at__date__gte=start,
            status=Transmission.Status.BOUNCED,
        )
        .annotate(day=TruncDate("message__created_at"))
        .values("day")
        .annotate(
            hard=Count("id", filter=Q(code__gte=500)),
            soft=Count("id", filter=Q(code__lt=500)),
        )
    )
    rows = list(rows)
    return (
        {row["day"]: row["hard"] for row in rows},
        {row["day"]: row["soft"] for row in rows},
    )


def complaints_per_day(org, start):
    """Return the complaint count per day since `start`."""
    reports = (
        FblReport.objects.filter(
            org=org,
            created_at__date__gte=start,
            source=FblReport.Source.PROVIDER,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    complaints = {row["day"]: row["count"] for row in reports}
    held = (
        OutgoingMessage.objects.filter(
            org=org,
            created_at__date__gte=start,
            status=OutgoingMessage.Status.HELD,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    for row in held:
        complaints[row["day"]] = complaints.get(row["day"], 0) + row["count"]
    return complaints


def share_of_limit(rate, limit):
    """Return `rate` as a percentage of `limit`, or None without a rate."""
    return round(rate / limit * 100, 1) if rate is not None else None


def rate_chart(rows, key, label, color, subtitle):
    """
    Return one rate chart, drawn as a share of its own limit.

    The limit sits on the 100 per cent line, so a rate reads as how much of
    the allowed rate the organization uses, and a rate over the limit shows
    above that line.
    """
    return {
        "series": [
            {
                "key": key,
                "label": label,
                "color": color,
                "dataset": "type: 'line'",
            }
        ],
        "rows": rows,
        "subtitle": subtitle,
        "threshold": {"value": 100, "label": gettext("Limit")},
        "y_scale": {"stacked": "false", "percent": True},
    }


def build_reputation_chart(org):
    """
    Return the per-day rates of one org, ready for one chart per rate.

    Counts provider FBL reports and outgoing messages held as spam as
    complaints. Values accumulate from the start of the evaluation
    window (`settings.RELAY_REPUTATION_WINDOW_DAYS`), so the last point
    equals the rates the reputation check evaluates. Each row carries its
    rates as a share of the matching limit, which puts that limit on the
    100 per cent line of the rate's own chart.
    """
    window_days = settings.RELAY_REPUTATION_WINDOW_DAYS
    start = timezone.localdate() - timedelta(days=window_days - 1)

    sent_counts = sent_per_day(org, start)
    hard_bounce_counts, soft_bounce_counts = bounced_per_day(org, start)
    complaint_counts = complaints_per_day(org, start)

    days_list = [start + timedelta(days=offset) for offset in range(window_days)]
    bounce_limit = settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD * 100
    complaint_limit = settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD * 100

    def cumulative(counts):
        counts = [counts.get(day, 0) for day in days_list]
        return [sum(counts[: index + 1]) for index in range(len(days_list))]

    sent_cumulative = cumulative(sent_counts)
    hard_bounce_cumulative = cumulative(hard_bounce_counts)
    soft_bounce_cumulative = cumulative(soft_bounce_counts)
    complaint_cumulative = cumulative(complaint_counts)

    def rate(count_cumulative):
        return [
            round(count / sent_total * 100, 4)
            if (sent_total := sent_cumulative[index])
            else None
            for index, count in enumerate(count_cumulative)
        ]

    hard_bounce_rates = rate(hard_bounce_cumulative)
    complaint_rates = rate(complaint_cumulative)
    rows = [
        {
            "day": day.isoformat(),
            "sent": sent_cumulative[index],
            "hard_bounced": hard_bounce_cumulative[index],
            "soft_bounced": soft_bounce_cumulative[index],
            "complained": complaint_cumulative[index],
            "hard_bounce_rate": hard_bounce_rates[index],
            "complaint_rate": complaint_rates[index],
            "hard_bounce_share": share_of_limit(hard_bounce_rates[index], bounce_limit),
            "complaint_share": share_of_limit(complaint_rates[index], complaint_limit),
        }
        for index, day in enumerate(days_list)
    ]
    return {
        "rows": rows,
        "bounce_chart": rate_chart(
            rows,
            key="hard_bounce_share",
            label=gettext("Hard bounce rate"),
            color=REPUTATION_CHART_COLORS["hard_bounce_rate"],
            subtitle=gettext("%(count)s hard bounces of %(sent)s sent, limit %(limit)s")
            % {
                "count": intcomma(hard_bounce_cumulative[-1]),
                "sent": intcomma(sent_cumulative[-1]),
                "limit": f"{bounce_limit:.2f}%",
            },
        ),
        "complaint_chart": rate_chart(
            rows,
            key="complaint_share",
            label=gettext("Complaint rate"),
            color=REPUTATION_CHART_COLORS["complaint_rate"],
            subtitle=gettext("%(count)s complaints of %(sent)s sent, limit %(limit)s")
            % {
                "count": intcomma(complaint_cumulative[-1]),
                "sent": intcomma(sent_cumulative[-1]),
                "limit": f"{complaint_limit:.2f}%",
            },
        ),
    }


def build_volume_chart(org):
    """
    Return the cumulative sending volume of this month and the last one.

    One point per day of the current month: the running total of the
    messages relay accepted up to that day, this month and the same day
    of the last month. The free plan limit rides along as a threshold
    line, so the chart shows how far the month has come against it.
    """
    today = timezone.localdate()
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    next_month = (today + timedelta(days=32)).replace(day=1)
    days_in_month = (next_month - this_month).days

    counts = (
        OutgoingMessage.objects.filter(
            org=org,
            created_at__date__gte=last_month,
            created_at__date__lt=next_month,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    per_day = {row["day"]: row["count"] for row in counts}

    rows = []
    last_total = this_total = 0
    for offset in range(days_in_month):
        day = this_month + timedelta(days=offset)
        last_day = last_month + timedelta(days=offset)
        has_last_day = last_day < this_month
        if has_last_day:
            last_total += per_day.get(last_day, 0)
        this_total += per_day.get(day, 0)
        rows.append(
            {
                "day": day.isoformat(),
                "last_month": last_total if has_last_day else None,
                "this_month": this_total if day <= today else None,
            }
        )

    # A last month with more days than this one keeps its tail in the final
    # point, so both lines end at a real month total.
    tail = last_month + timedelta(days=days_in_month)
    while tail < this_month:
        last_total += per_day.get(tail, 0)
        tail += timedelta(days=1)
    if rows[-1]["last_month"] is not None:
        rows[-1]["last_month"] = last_total

    return {
        "series": [
            {
                "key": "last_month",
                "label": gettext("Last month"),
                "color": REPUTATION_CHART_COLORS["last_month"],
                "dataset": "type: 'line'",
            },
            {
                "key": "this_month",
                "label": gettext("This month"),
                "color": REPUTATION_CHART_COLORS["this_month"],
                "dataset": "type: 'line'",
            },
        ],
        "rows": rows,
        "x_day": True,
        "subtitle": gettext("Cumulative, against the free tier"),
        "threshold": {
            "value": settings.RELAY_FREE_MONTHLY_MESSAGES,
            "label": gettext("Free tier"),
        },
        "y_scale": {"stacked": "false"},
    }
