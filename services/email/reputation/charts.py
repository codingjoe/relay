from datetime import timedelta

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
}


def build_reputation_chart(org):
    """Return chart data for reputation metrics grouped by day.

    Tracks sent, hard bounces, soft bounces, and FBL complaints over the
    chart window.
    """
    start = timezone.localdate() - timedelta(days=CHART_DAYS - 1)

    # Daily sent counts
    sent_rows = (
        OutgoingMessage.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    sent_counts = {row["day"]: row["count"] for row in sent_rows}

    # Daily hard bounce counts (5xx)
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

    # Daily soft bounce counts (4xx)
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

    # Daily FBL complaint counts
    complaint_rows = (
        FblReport.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Count("id"))
    )
    complaint_counts = {row["day"]: row["count"] for row in complaint_rows}

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
    return {
        "series": series,
        "rows": [
            {
                "day": day.isoformat(),
                "sent": sent_counts.get(day, 0),
                "hard_bounced": hard_bounce_counts.get(day, 0),
                "soft_bounced": soft_bounce_counts.get(day, 0),
                "complained": complaint_counts.get(day, 0),
            }
            for day in days_list
        ],
    }
