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


TIMELINE_COLORS = {
    "sent": "var(--color-chart-green)",
    "failed": "var(--color-chart-red)",
}


def build_incoming_timeline(message, deliveries):
    """
    Yield profile chart events for an incoming message.

    The reception opens the timeline as an instantaneous event; every
    webhook delivery follows with its own measured duration.
    """
    tls = " · ".join(
        part for part in (message.tls_version, message.tls_cipher) if part
    ) or ("plaintext" if not message.received_with_tls else "")
    yield {
        "name": (
            f"received ({message.receiving_domain})"
            if message.receiving_domain
            else "received"
        ),
        "color": "var(--color-chart-blue)",
        "start": int(message.created_at.timestamp() * 1000),
        "end": int(message.created_at.timestamp() * 1000),
        "duration": 0,
        "ips": "",
        "tls": tls,
        "transcript": f"reception-{message.pk}",
    }
    for delivery in deliveries:
        yield {
            "name": (
                f"{delivery.get_status_display()}"
                f" ({delivery.webhook.signing_key.key_id})"
            ),
            "color": TIMELINE_COLORS[delivery.status],
            "start": int(delivery.started_at.timestamp() * 1000),
            "end": int(delivery.finished_at.timestamp() * 1000),
            "duration": (delivery.finished_at - delivery.started_at).total_seconds()
            * 1000,
            "ips": "",
            "tls": "",
            "transcript": (
                f"delivery-{delivery.pk}"
                if delivery.response_code or delivery.response_body
                else ""
            ),
        }
