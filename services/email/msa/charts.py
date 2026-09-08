import datetime

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from abstract.charts import CHART_DAYS, build_chart_data

from .models import OutgoingMessage, SuppressionEntry, Transmission

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
    "spam-check": "var(--color-chart-gray)",
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
    target = transmission.mx_host or transmission.submission_ip_address or ""
    name = transmission.get_status_display()
    if target:
        name = f"{name} → {target}"
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
        "name": name,
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


def timing_event(timing):
    """Return one profile chart event for an internal processing stage."""
    return {
        "name": timing.stage.replace("-", " "),
        "color": TIMELINE_COLORS.get(timing.stage, "var(--color-chart-gray)"),
        "start": int(timing.started_at.timestamp() * 1000),
        "end": int(timing.finished_at.timestamp() * 1000),
        "duration": (timing.finished_at - timing.started_at).total_seconds() * 1000,
        "ips": "",
        "tls": "",
        "transcript": "",
    }


def build_timeline(timings):
    """
    Return profile chart events for a message's timings and transmissions.

    Every event spans its own measured start and finish, so the chart shows
    real leg durations and the gaps between bars show queueing and retry
    delays the way a browser network waterfall does.
    """
    events = []
    for timing in timings:
        try:
            transmission = timing.transmission
        except Transmission.DoesNotExist:
            events.append(timing_event(timing))
        else:
            events.append(transmission_event(transmission))
    return events
