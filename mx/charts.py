"""Chart data builders for incoming messages and TLS-RPT reports."""

from datetime import timedelta

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import IncomingMessage, TlsFailure, TlsReport

CHART_COLORS = {
    "delivered": "var(--color-success)",
    "webhook_sent": "var(--color-success)",
    "received": "var(--color-muted-foreground)",
    "bounced": "var(--color-warning)",
    "dropped": "var(--color-destructive)",
    "webhook_failed": "var(--color-destructive)",
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


def build_incoming_chart(org, days=CHART_DAYS):
    """Return chart data for incoming messages grouped by status."""
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        IncomingMessage.objects.filter(org=org, received_at__date__gte=start)
        .annotate(day=TruncDate("received_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(IncomingMessage.Status),
        CHART_COLORS,
        start,
        "status",
        days=days,
    )


def build_tls_chart(org, days=CHART_DAYS):
    """Return chart data for TLS failure counts grouped by result type."""
    start = timezone.localdate() - timedelta(days=days - 1)
    rows = (
        TlsFailure.objects.filter(
            report__org=org,
            report__report_status=TlsReport.Status.PARSED,
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
