import datetime

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import IncomingMessage, TlsFailure

CHART_COLORS = {
    "received": "var(--color-chart-green)",
    "quarantined": "var(--color-chart-yellow)",
    "webhook_sent": "var(--color-chart-green-deep)",
    "webhook_failed": "var(--color-chart-red)",
    "dropped": "var(--color-chart-red)",
}

TLS_CHART_COLORS = {
    "starttls-not-supported": "var(--color-chart-red)",
    "certificate-expired": "var(--color-chart-yellow)",
    "certificate-not-trusted": "var(--color-chart-red)",
    "certificate-name-mismatch": "var(--color-chart-yellow)",
    "tls-version-invalid": "var(--color-chart-yellow)",
    "tlsa-invalid": "var(--color-chart-yellow)",
    "dane-required": "var(--color-chart-yellow)",
    "sts-policy-invalid": "var(--color-chart-yellow)",
    "sts-webpki-invalid": "var(--color-chart-yellow)",
    "other": "var(--color-chart-gray)",
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
