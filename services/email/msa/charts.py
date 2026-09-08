import datetime

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import OutgoingMessage, SpamCheck, SuppressionEntry, Transmission

CHART_COLORS = {
    "sent": "var(--color-chart-green)",
    "pending": "var(--color-chart-gray)",
    "held": "var(--color-chart-yellow)",
    "bounced": "var(--color-chart-orange)",
    "failed": "var(--color-chart-red)",
    "dropped": "var(--color-chart-red)",
    "suppressed": "var(--color-chart-gray)",
}

SUPPRESSION_CHART_COLORS = {
    "bounce": "var(--color-chart-red)",
    "manual": "var(--color-chart-gray)",
}

TIMELINE_COLORS = {
    "submitted": "var(--color-chart-blue)",
    "sent": "var(--color-chart-green)",
    "retry": "var(--color-chart-yellow)",
    "failed": "var(--color-chart-red)",
    "bounced": "var(--color-chart-red)",
}


def build_outgoing_chart(org):
    """Return chart data for outgoing messages grouped by status."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        OutgoingMessage.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day", "status")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(OutgoingMessage.Status),
        CHART_COLORS,
        start,
        "status",
    )


def build_suppression_chart(org):
    """Return chart data for suppression entries grouped by reason."""
    start = timezone.localdate() - datetime.timedelta(days=CHART_DAYS - 1)
    rows = (
        SuppressionEntry.objects.filter(org=org, created_at__date__gte=start)
        .annotate(day=TruncDate("created_at"))
        .values("day", "reason")
        .annotate(count=Count("id"))
    )
    return build_chart_data(
        rows,
        list(SuppressionEntry.Reason),
        SUPPRESSION_CHART_COLORS,
        start,
        "reason",
    )


def transmission_event(transmission):
    """Return one profile chart event for a transmission."""
    tls = " · ".join(
        part
        for part in (
            transmission.get_tls_mode_display(),
            transmission.tls_version,
            transmission.tls_cipher,
        )
        if part
    )
    return {
        "name": transmission.label,
        "color": TIMELINE_COLORS[transmission.status],
        "start": int(transmission.started_at.timestamp() * 1000),
        "end": int(transmission.finished_at.timestamp() * 1000),
        "duration": (transmission.finished_at - transmission.started_at).total_seconds()
        * 1000,
        "ips": (
            f"{transmission.sending_mta_ip_address or '-'} →"
            f" {transmission.receiving_mx_ip_address or '-'}"
            if (
                transmission.sending_mta_ip_address
                or transmission.receiving_mx_ip_address
            )
            else ""
        ),
        "tls": tls,
        "transcript": (
            f"transcript-{transmission.pk}"
            if transmission.output or transmission.details or transmission.log_id
            else ""
        ),
    }


def spam_check_event(spam_check):
    """Return one profile chart event for a spam check."""
    return {
        "name": spam_check.label,
        "color": "var(--color-chart-gray)",
        "start": int(spam_check.started_at.timestamp() * 1000),
        "end": int(spam_check.finished_at.timestamp() * 1000),
        "duration": (spam_check.finished_at - spam_check.started_at).total_seconds()
        * 1000,
        "ips": "",
        "tls": "",
        "transcript": "",
    }


def build_timeline(timings):
    """
    Yield profile chart events for a message's timings and transmissions.

    Every event spans its own measured start and finish, so the chart shows
    real leg durations and the gaps between bars show queueing and retry
    delays the way a browser network waterfall does.
    """
    for timing in sorted(
        timings, key=lambda timing: (timing.started_at, timing.created_at)
    ):
        match timing:
            case Transmission():
                yield transmission_event(timing)
            case SpamCheck():
                yield spam_check_event(timing)
