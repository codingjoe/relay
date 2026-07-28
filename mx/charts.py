"""Chart data builder for incoming messages."""

from datetime import timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import IncomingMessage

CHART_COLORS = {
    "delivered": "var(--color-success)",
    "webhook_sent": "var(--color-success)",
    "received": "var(--color-muted-foreground)",
    "bounced": "var(--color-warning)",
    "dropped": "var(--color-destructive)",
    "webhook_failed": "var(--color-destructive)",
}


def build_incoming_chart(org, days=CHART_DAYS):
    """Build a stacked line chart of incoming messages by status."""
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        IncomingMessage.objects.filter(org=org, received_at__date__gte=start)
        .annotate(day=TruncDate("received_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(IncomingMessage.Status),
        CHART_COLORS,
        start,
        "status",
        days=days,
    )
