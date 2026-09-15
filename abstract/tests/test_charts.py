import datetime

from django.db.models import TextChoices

from abstract.charts import CHART_DAYS, build_chart_data


class Status(TextChoices):
    PASS = "pass", "Pass"
    FAIL = "fail", "Fail"


COLORS = {"pass": "green", "fail": "red"}


class TestBuildChartData:
    def test_build_chart_data__returns_series_for_all_choices(self):
        result = build_chart_data(
            [], list(Status), COLORS, datetime.date(2026, 1, 1), "status"
        )
        assert len(result["series"]) == 2
        assert result["series"][0]["key"] == "pass"
        assert result["series"][0]["color"] == "green"

    def test_build_chart_data__returns_rows_for_chart_days(self):
        result = build_chart_data(
            [], list(Status), COLORS, datetime.date(2026, 1, 1), "status"
        )
        assert len(result["rows"]) == CHART_DAYS
        assert result["rows"][0]["day"] == "2026-01-01"

    def test_build_chart_data__fills_zero_for_missing_days(self):
        result = build_chart_data(
            [], list(Status), COLORS, datetime.date(2026, 1, 1), "status"
        )
        assert result["rows"][0]["pass"] == 0
        assert result["rows"][0]["fail"] == 0

    def test_build_chart_data__aggregates_counts_from_rows(self):
        start = datetime.date(2026, 1, 1)
        rows = [
            {"day": start, "status": "pass", "count": 5},
            {"day": start, "status": "fail", "count": 3},
        ]
        result = build_chart_data(rows, list(Status), COLORS, start, "status")
        assert result["rows"][0]["pass"] == 5
        assert result["rows"][0]["fail"] == 3

    def test_build_chart_data__uses_gray_color_for_unknown_choice(self):
        class Extra(TextChoices):
            UNKNOWN = "unknown", "Unknown"

        result = build_chart_data(
            [], [Extra.UNKNOWN], {}, datetime.date(2026, 1, 1), "status"
        )
        assert result["series"][0]["color"] == "var(--color-chart-gray)"
