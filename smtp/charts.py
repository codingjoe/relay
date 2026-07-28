"""Chart data builder for outgoing messages."""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import OutgoingMessage

CHART_COLORS = {
    "delivered": "var(--color-success)",
    "sent": "var(--color-primary)",
    "pending": "var(--color-muted-foreground)",
    "held": "var(--color-warning)",
    "bounced": "var(--color-warning)",
    "failed": "var(--color-destructive)",
    "dropped": "var(--color-destructive)",
}


def build_outgoing_chart(org, days=CHART_DAYS):
    """Build a stacked line chart of outgoing messages by status."""
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        OutgoingMessage.objects.filter(org=org, received_at__date__gte=start)
        .annotate(day=TruncDate("received_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(OutgoingMessage.Status),
        CHART_COLORS,
        start,
        "status",
        days=days,
    )
