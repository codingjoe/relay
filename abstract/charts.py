"""Shared chart data builder for stacked line charts across apps."""

from datetime import timedelta

CHART_DAYS = 30
CHART_DAYS_SHORT = 7

# Message status colors shared between outgoing and incoming charts.
MESSAGE_CHART_COLORS = {
    # Positive outcome: green.
    "delivered": "var(--color-success)",
    "webhook_sent": "var(--color-success)",
    # In-flight: brand primary / muted.
    "sent": "var(--color-primary)",
    "pending": "var(--color-muted-foreground)",
    "received": "var(--color-muted-foreground)",
    # Transient problem: amber.
    "held": "var(--color-warning)",
    "bounced": "var(--color-warning)",
    # Terminal failure: red.
    "failed": "var(--color-destructive)",
    "dropped": "var(--color-destructive)",
    "webhook_failed": "var(--color-destructive)",
}

DMARC_CHART_COLORS = {
    "none": "var(--color-success)",
    "quarantine": "var(--color-warning)",
    "reject": "var(--color-destructive)",
}

TLS_CHART_COLORS = {
    "starttls-not-supported": "var(--color-destructive)",
    "certificate-expired": "var(--color-warning)",
    "certificate-not-trusted": "var(--color-destructive)",
    "certificate-name-mismatch": "var(--color-warning)",
    "tls-version-invalid": "var(--color-warning)",
    "tlsa-invalid": "var(--color-warning)",
    "dane-required": "var(--color-warning)",
    "sts-policy-invalid": "var(--color-warning)",
    "sts-webpki-invalid": "var(--color-warning)",
    "other": "var(--color-muted-foreground)",
}


def build_chart_data(rows, choices, colors, start, group_field, days=CHART_DAYS):
    """Build ``{"series": [...], "rows": [...]}`` for a stacked line chart.

    Args:
        rows: pre-aggregated queryset rows (list of dicts with keys ``"day"``,
            ``group_field``, and ``"count"``).
        choices: list of choice enum values (e.g. ``list(Model.Status)``).
        colors: dict mapping choice value to a CSS color string.
        start: the start ``date`` for the chart range.
        group_field: the key in each row dict that holds the group value
            (e.g. ``"status"``, ``"disposition"``).
        days: number of days for the chart range (default 30).
    """
    counts = {}
    for row in rows:
        counts.setdefault(row["day"], {})[row[group_field]] = row["count"]
    series = [
        {
            "key": choice.value,
            "label": str(choice.label),
            "color": colors.get(choice.value, "var(--color-muted-foreground)"),
        }
        for choice in choices
    ]
    days_list = [start + timedelta(days=offset) for offset in range(days)]
    return {
        "series": series,
        "rows": [
            {
                "day": day.isoformat(),
                **{
                    choice.value: counts.get(day, {}).get(choice.value, 0)
                    for choice in choices
                },
            }
            for day in days_list
        ],
    }
