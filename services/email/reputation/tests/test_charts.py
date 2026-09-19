from datetime import date, datetime, time

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from domains.models import Domain
from services.email.message.models import Transmission
from services.email.msa.models import OutgoingMessage
from services.email.reputation.charts import build_reputation_chart, build_volume_chart


def freeze_today(monkeypatch, day):
    monkeypatch.setattr(
        "services.email.reputation.charts.timezone.localdate",
        lambda: day,
    )


def make_message(org, day):
    """Create an outgoing message accepted at midday on `day`."""
    domain = Domain.objects.get_or_create(name="acme.com", org=org)[0]
    message = OutgoingMessage.objects.create(
        org=org,
        domain=domain,
        mail_from="sender@acme.com",
        rcpt_to="rcpt@example.com",
        raw_body=SimpleUploadedFile("message.eml", b"body"),
    )
    OutgoingMessage.objects.filter(pk=message.pk).update(
        created_at=timezone.make_aware(datetime.combine(day, time(hour=12)))
    )
    return message


@pytest.mark.django_db
class TestBuildReputationChart:
    """The reputation chart runs over the evaluation window."""

    def test_with_a_zero_window__counts_as_one_day(self, org, settings, monkeypatch):
        freeze_today(monkeypatch, date(2026, 9, 19))
        settings.RELAY_REPUTATION_WINDOW_DAYS = 0

        chart = build_reputation_chart(org)

        assert len(chart["rows"]) == 1
        assert chart["rows"][0]["day"] == "2026-09-19"
        assert chart["rows"][0]["hard_bounce_rate"] is None
        assert chart["rows"][0]["complaint_rate"] is None

    def test_with_a_negative_window__counts_as_one_day(
        self, org, settings, monkeypatch
    ):
        freeze_today(monkeypatch, date(2026, 9, 19))
        settings.RELAY_REPUTATION_WINDOW_DAYS = -7

        chart = build_reputation_chart(org)

        assert len(chart["rows"]) == 1
        assert chart["rows"][0]["day"] == "2026-09-19"

    def test_reports_the_cumulative_rates(self, org, settings, monkeypatch):
        freeze_today(monkeypatch, date(2026, 9, 19))
        settings.RELAY_REPUTATION_WINDOW_DAYS = 7
        make_message(org, date(2026, 9, 15))
        bounced = make_message(org, date(2026, 9, 16))
        Transmission.objects.create(
            message=bounced,
            status=Transmission.Status.BOUNCED,
            code=550,
            started_at=timezone.now(),
            finished_at=timezone.now(),
        )

        chart = build_reputation_chart(org)

        rows = chart["rows"]
        assert rows[2]["hard_bounce_rate"] == 0.0
        assert rows[3]["hard_bounce_rate"] == 50.0
        assert rows[-1]["hard_bounce_rate"] == 50.0
        assert rows[-1]["complaint_rate"] == 0.0


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

    def test_reports_the_cumulative_volume(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 9, 19))
        make_message(org, date(2026, 8, 10))
        make_message(org, date(2026, 9, 1))
        make_message(org, date(2026, 9, 1))
        make_message(org, date(2026, 9, 3))

        chart = build_volume_chart(org)

        rows = chart["rows"]
        assert rows[0]["last_month"] == 0
        assert rows[0]["this_month"] == 2
        assert rows[2]["this_month"] == 3
        assert rows[9]["last_month"] == 1
        assert rows[18]["this_month"] == 3
        assert rows[19]["this_month"] is None
        assert rows[-1]["this_month"] is None

    def test_reports_the_month_total(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 9, 19))
        make_message(org, date(2026, 8, 10))
        make_message(org, date(2026, 9, 1))
        make_message(org, date(2026, 9, 18))

        chart = build_volume_chart(org)

        assert chart["this_month_total"] == 2
        assert chart["rows"][-1]["last_month"] == 1

    def test_at_a_short_month__folds_the_previous_months_tail(self, org, monkeypatch):
        freeze_today(monkeypatch, date(2026, 2, 28))
        make_message(org, date(2026, 1, 15))
        make_message(org, date(2026, 1, 29))
        make_message(org, date(2026, 1, 30))
        make_message(org, date(2026, 1, 31))
        make_message(org, date(2026, 2, 28))

        chart = build_volume_chart(org)

        rows = chart["rows"]
        assert rows[13]["last_month"] == 0
        assert rows[14]["last_month"] == 1
        assert rows[-2]["last_month"] == 1
        assert rows[-1]["last_month"] == 4
        assert rows[-1]["this_month"] == 1
