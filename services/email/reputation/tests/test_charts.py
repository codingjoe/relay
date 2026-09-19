from datetime import date

import pytest

from services.email.reputation.charts import build_volume_chart


def freeze_today(monkeypatch, day):
    monkeypatch.setattr(
        "services.email.reputation.charts.timezone.localdate",
        lambda: day,
    )


@pytest.mark.django_db
class TestBuildVolumeChart:
    """The volume chart runs over the current month, and the one before it."""

    def test_covers_the_whole_month(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 9, 19))

        chart = build_volume_chart(org)

        assert len(chart["rows"]) == 30
        assert chart["rows"][0]["day"] == "2026-09-01"
        assert chart["rows"][-1]["day"] == "2026-09-30"

    def test_covers_a_short_month(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 2, 15))

        chart = build_volume_chart(org)

        assert len(chart["rows"]) == 28
        assert chart["rows"][0]["day"] == "2026-02-01"

    def test_at_a_month_end__stops_at_that_month(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 3, 31))

        chart = build_volume_chart(org)

        assert len(chart["rows"]) == 31
        assert chart["rows"][-1]["day"] == "2026-03-31"

    def test_at_a_short_month_end__stops_at_that_month(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 2, 28))

        chart = build_volume_chart(org)

        assert len(chart["rows"]) == 28
        assert chart["rows"][-1]["day"] == "2026-02-28"

    def test_at_a_year_end__stops_at_that_month(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 12, 31))

        chart = build_volume_chart(org)

        assert len(chart["rows"]) == 31
        assert chart["rows"][-1]["day"] == "2026-12-31"
