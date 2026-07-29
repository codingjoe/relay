from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import DmarcRecord, DmarcReport

DMARC_CHART_COLORS = {
    "none": "var(--color-success)",
    "quarantine": "var(--color-warning)",
    "reject": "var(--color-destructive)",
}


def build_dmarc_chart(org):
    """Return chart data for DMARC message counts grouped by disposition."""
    start = timezone.localdate() - timedelta(days=CHART_DAYS - 1)
    rows = (
        DmarcRecord.objects.filter(
            report__org=org,
            report__begin_at__date__gte=start,
        )
        .annotate(day=TruncDate("report__begin_at"))
        .values("day", "disposition")
        .annotate(count=Sum("count"))
    )
    return build_chart_data(
        rows,
        list(DmarcReport.Disposition),
        DMARC_CHART_COLORS,
        start,
        "disposition",
    )
