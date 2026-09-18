import datetime

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import SuppressionEntry

SUPPRESSION_CHART_COLORS = {
    "bounce": "var(--color-chart-red)",
    "manual": "var(--color-chart-gray)",
}

TIMELINE_COLORS = {
    "submitted": "var(--color-chart-blue)",
    "sent": "var(--color-chart-green)",
    "retry": "var(--color-chart-yellow)",
    "failed": "var(--color-chart-red)",
    "bounced": "var(--color-chart-red)",
}


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
