"""Chart data builders for DMARC and TLS-RPT reports."""

from datetime import timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import DmarcRecord, DmarcReport, TlsFailure, TlsReport

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


def build_dmarc_chart(org, days=CHART_DAYS):
    """Build a stacked line chart of DMARC message counts by disposition."""
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        DmarcRecord.objects.filter(
            report__org=org,
            report__status=DmarcReport.Status.PARSED,
            report__begin_at__date__gte=start,
        )
        .annotate(day=TruncDate("report__begin_at"))
        .values("day", "disposition")
        .annotate(count=Sum("count"))
    )
    return build_chart_data(
        rows,
        list(DmarcReport.Disposition),
        DMARC_CHART_COLORS,
        start,
        "disposition",
        days=days,
    )


def build_tls_chart(org, days=CHART_DAYS):
    """Build a stacked line chart of TLS failure counts by result type."""
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        TlsFailure.objects.filter(
            report__org=org,
            report__status=TlsReport.Status.PARSED,
            report__begin_at__date__gte=start,
        )
        .annotate(day=TruncDate("report__begin_at"))
        .values("day", "result_type")
        .annotate(count=Sum("count"))
    )
    return build_chart_data(
        rows,
        list(TlsFailure.ResultType),
        TLS_CHART_COLORS,
        start,
        "result_type",
        days=days,
    )
