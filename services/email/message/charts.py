import datetime

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

MESSAGE_KINDS = {
    "outgoing": "outgoingmessage",
    "incoming": "incomingmessage",
}


def get_message_model(model_name: str):
    """
    Return the concrete `Message` subclass with this model name.

    The shared app reads its own subclasses, so it needs no sibling import
    and no content type query. `Message.status_choices` reads them the same
    way.
    """
    return next(
        subclass
        for subclass in Message.__subclasses__()
        if subclass._meta.model_name == model_name
    )


def status_colors(status_class) -> dict:
    """Return the chart color of every status, taken from its badge variant."""
    return {
        status.value: STATUS_CHART_COLORS.get(
            status.badge_variant, "var(--color-chart-gray)"
        )
        for status in status_class
    }


def build_kind_charts(messages, model_names) -> list:
    """
    Return one status chart per message kind, in the order of `model_names`.

    One query counts every kind. Series colors follow the status badge
    variants, so a status reads the same in the list and in the chart.
    Callers pass the queryset the list shows, so the chart counts what the
    filters select.
    """
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        messages.filter(
            content_type__model__in=model_names,
            created_at__date__gte=start,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day", "content_type__model", "status")
        .annotate(count=Count("id"))
    )
    charts = []
    for model_name in model_names:
        status_class = get_message_model(model_name).Status
        charts.append(
            build_chart_data(
                [row for row in rows if row["content_type__model"] == model_name],
                list(status_class),
                status_colors(status_class),
                start,
                "status",
            )
        )
    return charts


def build_direction_chart(messages) -> dict:
    """
    Return one chart of outgoing and incoming messages of `messages`.

    Outgoing counts stay positive and incoming counts negate, so the
    outgoing bars rise above the axis and the incoming bars hang below it.
    Series keys and labels carry the direction, because both kinds define a
    status named `dropped`.
    """
    outgoing_direction, incoming_direction = MESSAGE_KINDS
    outgoing, incoming = build_kind_charts(messages, list(MESSAGE_KINDS.values()))
    return {
        "y_scale": {"diverging": True},
        "series": [
            {
                **series,
                "key": f"{direction}_{series['key']}",
                "label": f"{_(direction)} {series['label']}",
            }
            for direction, chart in zip(MESSAGE_KINDS, (outgoing, incoming))
            for series in chart["series"]
        ],
        "rows": [
            {"day": outgoing_row["day"]}
            | {
                f"{outgoing_direction}_{key}": value
                for key, value in outgoing_row.items()
                if key != "day"
            }
            | {
                f"{incoming_direction}_{key}": -value
                for key, value in incoming_row.items()
                if key != "day"
            }
            for outgoing_row, incoming_row in zip(outgoing["rows"], incoming["rows"])
        ],
    }
