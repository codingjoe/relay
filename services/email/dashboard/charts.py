import datetime
from typing import NamedTuple

from django.db import models
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from abstract.charts import CHART_DAYS, build_chart_data
from services.email.dmarc.models import DmarcFailureReport, DmarcRecord, DmarcReport
from services.email.mta.models import TlsReport
from services.email.reputation.models import FblReport


class ReportType(models.TextChoices):
    DMARC = "dmarc", _("DMARC")
    FAILURES = "failures", _("DMARC failures")
    TLS = "tls", _("TLS")
    FBL = "fbl", _("FBL")


class ChartSeries(NamedTuple):
    value: str
    label: str


DMARC_SERIES = (
    (
        ChartSeries("dmarc-pass", _("DMARC passed")),
        DmarcReport.Disposition.NONE,
        "var(--color-chart-green)",
    ),
    (
        ChartSeries("dmarc-quarantine", _("DMARC quarantined")),
        DmarcReport.Disposition.QUARANTINE,
        "var(--color-chart-yellow)",
    ),
    (
        ChartSeries("dmarc-reject", _("DMARC rejected")),
        DmarcReport.Disposition.REJECT,
        "var(--color-chart-red)",
    ),
)


def build_report_chart(org, report_types):
    """Return chart data per day, grouped by report series."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = []
    series = []
    colors = {}

    def add(choice, color, counts):
        series.append(choice)
        colors[choice.value] = color
        rows.extend(
            {
                "day": row["day"],
                "series": choice.value,
                "count": row["count"] or 0,
            }
            for row in counts
        )

    if ReportType.DMARC in report_types:
        for choice, disposition, color in DMARC_SERIES:
            counts = (
                DmarcRecord.objects.filter(
                    report__org=org,
                    report__created_at__date__gte=start,
                    disposition=disposition,
                )
                .annotate(day=TruncDate("report__created_at"))
                .values("day")
                .annotate(count=Sum("count"))
            )
            add(choice, color, counts)

    if ReportType.FAILURES in report_types:
        counts = (
            DmarcFailureReport.objects.filter(org=org, created_at__date__gte=start)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("pk"))
        )
        add(
            ChartSeries("failures", _("DMARC failures")),
            "var(--color-chart-gray)",
            counts,
        )

    if ReportType.TLS in report_types:
        counts = (
            TlsReport.objects.filter(org=org, created_at__date__gte=start)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Sum("failed_session_count"))
        )
        add(
            ChartSeries("tls", _("TLS failures")),
            "var(--color-chart-blue)",
            counts,
        )

    if ReportType.FBL in report_types:
        counts = (
            FblReport.objects.filter(org=org, created_at__date__gte=start)
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(count=Count("pk"))
        )
        add(ChartSeries("fbl", _("FBL")), "var(--color-chart-orange)", counts)

    return build_chart_data(rows, series, colors, start, "series")
