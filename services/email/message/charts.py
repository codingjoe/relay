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

    Reads the subclasses instead of importing a sibling app, like
    `Message.status_choices` does.
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

    Counts the queryset the list shows, so the chart follows the filters, and
    colors each status like its badge, so it reads the same in both places.
    Incoming charts filter through the `IncomingMessage` parent, so report
    subtypes count with the rest.
    """
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    messages = messages.filter(created_at__date__gte=start)
    incoming_model_name = MESSAGE_KINDS["incoming"]
    charts = []
    for model_name in model_names:
        if model_name == incoming_model_name:
            kind_messages = messages.filter(incomingmessage__isnull=False)
        else:
            kind_messages = messages.filter(content_type__model=model_name)
        status_class = get_message_model(model_name).Status
        rows = (
            kind_messages.annotate(day=TruncDate("created_at"))
            .values("day", "status")
            .annotate(count=Count("id"))
        )
        charts.append(
            build_chart_data(
                rows,
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

    Outgoing counts rise above the axis and incoming counts hang below it.
    Keys carry the direction, because both kinds define a status named
    `dropped`.
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
