"""Shared chart data builder for stacked line charts across apps."""

from datetime import timedelta

CHART_DAYS = 30
CHART_DAYS_SHORT = 7


def build_chart_data(rows, choices, colors, start, group_field, days=CHART_DAYS):
    """Build chart series and rows for a stacked line chart.

    - **rows**: pre-aggregated queryset rows (list of dicts with keys `"day"`,
      `group_field`, and `"count"`).
    - **choices**: list of choice enum values (e.g. `list(Model.Status)`).
    - **colors**: dict mapping choice value to a CSS color string.
    - **start**: the start `date` for the chart range.
    - **group_field**: the key in each row dict that holds the group value
      (e.g. `"status"`, `"disposition"`).
    - **days**: number of days for the chart range (default 30).
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
