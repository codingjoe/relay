import datetime

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

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


def build_direction_chart(org) -> dict:
    """
    Return one chart of outgoing and incoming messages for one org.

    Outgoing counts stay positive and incoming counts negate, so the
    outgoing bars rise above the axis and the incoming bars hang below it.
    Series keys and labels carry the direction, because both kinds define a
    status named `dropped`.
    """
    outgoing = build_message_chart(org, "outgoingmessage")
    incoming = build_message_chart(org, "incomingmessage")
    return {
        "y_scale": {"diverging": True},
        "series": [
            {
                **series,
                "key": f"{direction}_{series['key']}",
                "label": f"{_(direction)} {series['label']}",
            }
            for direction, chart in (("outgoing", outgoing), ("incoming", incoming))
            for series in chart["series"]
        ],
        "rows": [
            {"day": outgoing_row["day"]}
            | {
                f"outgoing_{key}": count
                for key, count in outgoing_row.items()
                if key != "day"
            }
            | {
                f"incoming_{key}": -count
                for key, count in incoming_row.items()
                if key != "day"
            }
            for outgoing_row, incoming_row in zip(
                outgoing["rows"], incoming["rows"], strict=True
            )
        ],
    }
