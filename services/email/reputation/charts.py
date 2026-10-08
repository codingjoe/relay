from calendar import monthrange
from datetime import timedelta
from itertools import accumulate

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext, ngettext

from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage

from .models import FblReport

REPUTATION_CHART_COLORS = {
    "hard_bounce_rate": "var(--color-chart-red)",
    "soft_bounce_rate": "var(--color-chart-yellow)",
    "complaint_rate": "var(--color-chart-orange)",
    "this_month": "var(--color-chart-green)",
    "last_month": "var(--color-chart-gray)",
}


def sent_per_day(org, start):
    """Return the deliverable outgoing message count per day since `start`."""
    rows = (
        OutgoingMessage.objects.filter(org=org, created_at__date__gte=start)
        .exclude(status=OutgoingMessage.Status.SANDBOXED)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    return {row["day"]: row["count"] for row in rows}


def bounced_per_day(org, start):
    """Return the hard bounce count per day since `start`."""
    rows = (
        Transmission.objects.filter(
            message__org=org,
            message__created_at__date__gte=start,
            status=Transmission.Status.BOUNCED,
            code__gte=500,  # 5xx is a hard bounce, 4xx a soft one
        )
        .annotate(day=TruncDate("message__created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    return {row["day"]: row["count"] for row in rows}


def soft_bounces_per_day(org, start):
    """Return the daily count of messages whose delivery a 4xx refusal ended."""
    rows = (
        OutgoingMessage.objects.filter(
            org=org,
            created_at__date__gte=start,
            status=OutgoingMessage.Status.FAILED,
            transmissions__status=Transmission.Status.FAILED,
            transmissions__code__gte=400,
            transmissions__code__lt=500,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id", distinct=True))
    )
    return {row["day"]: row["count"] for row in rows}


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


def rate_chart(rows, key, label, color, limit, subtitle):
    """Return the payload for one plotted series, with an optional limit line."""
    return {
        "series": [
            {
                "key": key,
                "label": label,
                "color": color,
                "type": "line",
            }
        ],
        "rows": rows,
        "subtitle": subtitle,
        "threshold": (
            {"value": limit, "label": gettext("Limit")} if limit is not None else None
        ),
        "y_scale": {"stacked": False, "percent": True},
    }


def build_reputation_chart(org):
    """
    Return the hard bounce, soft bounce, and complaint rates of one organization.

    The rates are cumulative and cover the last
    `RELAY_REPUTATION_WINDOW_DAYS` days. The soft bounce rate is display-only:
    only the hard bounce and complaint rates feed the suspension check.
    """
    window_days = max(settings.RELAY_REPUTATION_WINDOW_DAYS, 1)
    start = timezone.localdate() - timedelta(days=window_days - 1)

    sent_counts = sent_per_day(org, start)
    hard_bounce_counts = bounced_per_day(org, start)
    soft_bounce_counts = soft_bounces_per_day(org, start)
    complaint_counts = complaints_per_day(org, start)

    days_list = [start + timedelta(days=offset) for offset in range(window_days)]
    bounce_limit = settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD * 100
    complaint_limit = settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD * 100

    sent_cumulative = list(accumulate(sent_counts.get(day, 0) for day in days_list))
    hard_bounce_cumulative = list(
        accumulate(hard_bounce_counts.get(day, 0) for day in days_list)
    )
    soft_bounce_cumulative = list(
        accumulate(soft_bounce_counts.get(day, 0) for day in days_list)
    )
    complaint_cumulative = list(
        accumulate(complaint_counts.get(day, 0) for day in days_list)
    )

    def rate(count_cumulative):
        return [
            round(count / sent_total * 100, 4) if sent_total else None
            for count, sent_total in zip(count_cumulative, sent_cumulative)
        ]

    hard_bounce_rates = rate(hard_bounce_cumulative)
    soft_bounce_rates = rate(soft_bounce_cumulative)
    complaint_rates = rate(complaint_cumulative)
    rows = [
        {
            "day": day.isoformat(),
            "hard_bounce_rate": hard_bounce_rate,
            "soft_bounce_rate": soft_bounce_rate,
            "complaint_rate": complaint_rate,
        }
        for day, hard_bounce_rate, soft_bounce_rate, complaint_rate in zip(
            days_list, hard_bounce_rates, soft_bounce_rates, complaint_rates
        )
    ]
    return {
        "rows": rows,
        "hard_bounce_chart": rate_chart(
            rows,
            key="hard_bounce_rate",
            label=gettext("Hard bounce rate"),
            color=REPUTATION_CHART_COLORS["hard_bounce_rate"],
            limit=bounce_limit,
            subtitle=ngettext(
                "%(count)s hard bounce of %(sent)s sent, limit %(limit)s",
                "%(count)s hard bounces of %(sent)s sent, limit %(limit)s",
                hard_bounce_cumulative[-1],
            )
            % {
                "count": intcomma(hard_bounce_cumulative[-1]),
                "sent": intcomma(sent_cumulative[-1]),
                "limit": f"{bounce_limit:.2f}%",
            },
        ),
        "soft_bounce_chart": rate_chart(
            rows,
            key="soft_bounce_rate",
            label=gettext("Soft bounce rate"),
            color=REPUTATION_CHART_COLORS["soft_bounce_rate"],
            limit=None,
            subtitle=ngettext(
                "%(count)s soft bounce of %(sent)s sent",
                "%(count)s soft bounces of %(sent)s sent",
                soft_bounce_cumulative[-1],
            )
            % {
                "count": intcomma(soft_bounce_cumulative[-1]),
                "sent": intcomma(sent_cumulative[-1]),
            },
        ),
        "complaint_chart": rate_chart(
            rows,
            key="complaint_rate",
            label=gettext("Complaint rate"),
            color=REPUTATION_CHART_COLORS["complaint_rate"],
            limit=complaint_limit,
            subtitle=ngettext(
                "%(count)s complaint of %(sent)s sent, limit %(limit)s",
                "%(count)s complaints of %(sent)s sent, limit %(limit)s",
                complaint_cumulative[-1],
            )
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

    One point per day, this month and the same day of the last month, with
    the free tier as the threshold line.
    """
    today = timezone.localdate()
    this_month = today.replace(day=1)
    last_month = (this_month - timedelta(days=1)).replace(day=1)
    days_in_month = monthrange(today.year, today.month)[1]
    per_day = sent_per_day(org, last_month)

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

    # A last month with more days keeps its tail in the final point.
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
                "type": "line",
            },
            {
                "key": "this_month",
                "label": gettext("This month"),
                "color": REPUTATION_CHART_COLORS["this_month"],
                "type": "line",
            },
        ],
        "rows": rows,
        "this_month_total": this_total,
        "subtitle": gettext("Cumulative, against the free tier"),
        "threshold": {
            "value": settings.RELAY_FREE_MONTHLY_MESSAGES,
            "label": gettext("Free tier"),
        },
        "y_scale": {"stacked": False},
    }
