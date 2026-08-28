from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS
from services.email.msa.models import OutgoingMessage, Transmission

from .models import FblReport

REPUTATION_CHART_COLORS = {
    "sent": "var(--color-primary)",
    "hard_bounced": "var(--color-destructive)",
    "soft_bounced": "var(--color-warning)",
    "complained": "var(--color-destructive)",
    "hard_bounce_rate": "var(--color-destructive)",
    "complaint_rate": "var(--color-primary)",
    "hard_bounce_limit": "var(--color-muted-foreground)",
    "complaint_limit": "var(--color-muted-foreground)",
}


def build_reputation_chart(org):
    """Return per-day message counts, rates, and rate limits for one org.

    Counts provider FBL reports and outgoing messages held as spam as
    complaints over the `CHART_DAYS` window. Rates and limits are per
    cent, so they share one axis and can be plotted next to each other.
    """
    start = timezone.localdate() - timedelta(days=CHART_DAYS - 1)

    sent_rows = (
        OutgoingMessage.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    sent_counts = {row["day"]: row["count"] for row in sent_rows}

    hard_bounce_rows = (
        Transmission.objects.filter(
            message__org=org,
            message__created_at__date__gte=start,
            status=Transmission.Status.BOUNCED,
            code__gte=500,
        )
        .annotate(day=TruncDate("message__created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    hard_bounce_counts = {row["day"]: row["count"] for row in hard_bounce_rows}

    soft_bounce_rows = (
        Transmission.objects.filter(
            message__org=org,
            message__created_at__date__gte=start,
            status=Transmission.Status.BOUNCED,
            code__lt=500,
        )
        .annotate(day=TruncDate("message__created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    soft_bounce_counts = {row["day"]: row["count"] for row in soft_bounce_rows}

    complaint_rows = (
        FblReport.objects.filter(
            org=org,
            created_at__date__gte=start,
            source=FblReport.Source.PROVIDER,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    complaint_counts = {row["day"]: row["count"] for row in complaint_rows}

    held_spam_rows = (
        OutgoingMessage.objects.filter(
            org=org,
            created_at__date__gte=start,
            status=OutgoingMessage.Status.HELD,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    for row in held_spam_rows:
        complaint_counts[row["day"]] = (
            complaint_counts.get(row["day"], 0) + row["count"]
        )

    days_list = [start + timedelta(days=offset) for offset in range(CHART_DAYS)]
    series = [
        {
            "key": "sent",
            "label": "Sent",
            "color": REPUTATION_CHART_COLORS["sent"],
        },
        {
            "key": "hard_bounced",
            "label": "Hard bounces",
            "color": REPUTATION_CHART_COLORS["hard_bounced"],
        },
        {
            "key": "soft_bounced",
            "label": "Soft bounces",
            "color": REPUTATION_CHART_COLORS["soft_bounced"],
        },
        {
            "key": "complained",
            "label": "Complaints",
            "color": REPUTATION_CHART_COLORS["complained"],
        },
    ]
    bounce_limit = settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD * 100
    complaint_limit = settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD * 100

    def rate(counts):
        return [
            round(counts.get(day, 0) / sent_counts[day] * 100, 4)
            if sent_counts.get(day)
            else None
            for day in days_list
        ]

    hard_bounce_rates = rate(hard_bounce_counts)
    complaint_rates = rate(complaint_counts)
    rate_series = [
        {
            "key": "hard_bounce_rate",
            "label": "Hard bounce rate",
            "color": REPUTATION_CHART_COLORS["hard_bounce_rate"],
        },
        {
            "key": "complaint_rate",
            "label": "Complaint rate",
            "color": REPUTATION_CHART_COLORS["complaint_rate"],
        },
        {
            "key": "hard_bounce_limit",
            "label": "Hard bounce limit",
            "color": REPUTATION_CHART_COLORS["hard_bounce_limit"],
            "dataset": "stack: null, fill: false",
        },
        {
            "key": "complaint_limit",
            "label": "Complaint limit",
            "color": REPUTATION_CHART_COLORS["complaint_limit"],
            "dataset": "stack: null, fill: false",
        },
    ]
    return {
        "series": series,
        "rate_series": rate_series,
        "rows": [
            {
                "day": day.isoformat(),
                "sent": sent_counts.get(day, 0),
                "hard_bounced": hard_bounce_counts.get(day, 0),
                "soft_bounced": soft_bounce_counts.get(day, 0),
                "complained": complaint_counts.get(day, 0),
                "hard_bounce_rate": hard_bounce_rates[index],
                "complaint_rate": complaint_rates[index],
                "hard_bounce_limit": bounce_limit,
                "complaint_limit": complaint_limit,
            }
            for index, day in enumerate(days_list)
        ],
    }
