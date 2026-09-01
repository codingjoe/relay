import datetime

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import OutgoingMessage, SuppressionEntry

CHART_COLORS = {
    "delivered": "var(--color-chart-success)",
    "sent": "var(--color-chart-info)",
    "pending": "var(--color-chart-neutral)",
    "held": "var(--color-chart-warning)",
    "bounced": "var(--color-chart-warning)",
    "failed": "var(--color-chart-destructive)",
    "dropped": "var(--color-chart-destructive)",
}

SUPPRESSION_CHART_COLORS = {
    "bounce": "var(--color-chart-destructive)",
    "manual": "var(--color-chart-neutral)",
}


def build_outgoing_chart(org):
    """Return chart data for outgoing messages grouped by status."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        OutgoingMessage.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(OutgoingMessage.Status),
        CHART_COLORS,
        start,
        "status",
    )


def build_suppression_chart(org):
    """Return chart data for suppression entries grouped by reason."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        SuppressionEntry.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day", "reason")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(SuppressionEntry.Reason),
        SUPPRESSION_CHART_COLORS,
        start,
        "reason",
    )
