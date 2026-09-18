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


def count_message_rows(messages, model_names, start):
    """Return the per-day, per-status counts of the given message kinds."""
    return (
        messages.filter(
            content_type__model__in=model_names,
            created_at__date__gte=start,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day", "content_type__model", "status")
        .annotate(count=Count("id"))
    )


def build_message_chart(messages, model_name: str) -> dict:
    """
    Return chart data for one message kind of `messages`, grouped by status.

    Series colors follow the status badge variants, so a status reads the
    same in the list and in the chart. Callers pass the queryset the list
    shows, so the chart counts what the filters select.
    """
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = count_message_rows(messages, [model_name], start)
    status_class = get_message_model(model_name).Status
    return build_chart_data(
        rows,
        list(status_class),
        status_colors(status_class),
        start,
        "status",
    )


def build_direction_chart(messages) -> dict:
    """
    Return one chart of outgoing and incoming messages of `messages`.

    Outgoing counts stay positive and incoming counts negate, so the
    outgoing bars rise above the axis and the incoming bars hang below it.
    Series keys and labels carry the direction, because both kinds define a
    status named `dropped`. One query counts both kinds.
    """
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    model_names = list(MESSAGE_KINDS.values())
    rows = count_message_rows(messages, model_names, start)
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
    return merge_direction_charts(list(MESSAGE_KINDS), charts)


def merge_direction_charts(directions, charts) -> dict:
    """Mirror one chart per direction on the axis, outgoing first."""
    outgoing_direction, incoming_direction = directions
    outgoing_rows, incoming_rows = (chart["rows"] for chart in charts)
    return {
        "y_scale": {"diverging": True},
        "series": [
            {
                **series,
                "key": f"{direction}_{series['key']}",
                "label": f"{_(direction)} {series['label']}",
            }
            for direction, chart in zip(directions, charts, strict=True)
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
            for outgoing_row, incoming_row in zip(
                outgoing_rows, incoming_rows, strict=True
            )
        ],
    }
