import datetime

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import Message

STATUS_CHART_COLORS = {
    "success": "var(--color-chart-green)",
    "warning": "var(--color-chart-yellow)",
    "destructive": "var(--color-chart-red)",
    "outline": "var(--color-chart-gray)",
}


def build_message_chart(org, model_name: str) -> dict:
    """
    Return chart data for one message kind, grouped by status.

    The kind is a concrete `Message` subclass. The shared app resolves it
    through the content type, so it never imports a sibling app. Series
    colors follow the status badge variants, so a status reads the same in
    the list and in the chart.
    """
    status_class = ContentType.objects.get(model=model_name).model_class().Status
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        Message.objects.filter(
            org=org,
            content_type__model=model_name,
            created_at__date__gte=start,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    colors = {
        status.value: STATUS_CHART_COLORS.get(
            status.badge_variant, "var(--color-chart-gray)"
        )
        for status in status_class
    }
    return build_chart_data(rows, list(status_class), colors, start, "status")
