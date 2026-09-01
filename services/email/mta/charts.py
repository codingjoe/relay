import datetime

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import IncomingMessage, TlsFailure

CHART_COLORS = {
    "delivered": "var(--color-chart-success)",
    "webhook_sent": "var(--color-chart-success)",
    "received": "var(--color-chart-neutral)",
    "bounced": "var(--color-chart-warning)",
    "dropped": "var(--color-chart-destructive)",
    "webhook_failed": "var(--color-chart-destructive)",
}

TLS_CHART_COLORS = {
    "starttls-not-supported": "var(--color-chart-destructive)",
    "certificate-expired": "var(--color-chart-warning)",
    "certificate-not-trusted": "var(--color-chart-destructive)",
    "certificate-name-mismatch": "var(--color-chart-warning)",
    "tls-version-invalid": "var(--color-chart-warning)",
    "tlsa-invalid": "var(--color-chart-warning)",
    "dane-required": "var(--color-chart-warning)",
    "sts-policy-invalid": "var(--color-chart-warning)",
    "sts-webpki-invalid": "var(--color-chart-warning)",
    "other": "var(--color-chart-neutral)",
}


def build_incoming_chart(org):
    """Return chart data for incoming messages grouped by status."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        IncomingMessage.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(IncomingMessage.Status),
        CHART_COLORS,
        start,
        "status",
    )


def build_tls_chart(org):
    """Return chart data for TLS failure counts grouped by result type."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        TlsFailure.objects.filter(
            report__org=org,
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
    )
