"""Provide the unified transactional email dashboard."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from accounts.views import OrganizationScopedView
from domains.models import Domain
from mx.models import IncomingMessage
from smtp.models import OutgoingMessage

CHART_DAYS = 30
CHART_COLORS = {
    # Positive outcome: green.
    "delivered": "var(--color-success)",
    "webhook_sent": "var(--color-success)",
    # In-flight: brand primary.
    "sent": "var(--color-primary)",
    "pending": "var(--color-muted-foreground)",
    "received": "var(--color-muted-foreground)",
    # Transient problem: amber.
    "held": "var(--color-warning)",
    "bounced": "var(--color-warning)",
    # Terminal failure: red.
    "failed": "var(--color-destructive)",
    "dropped": "var(--color-destructive)",
    "webhook_failed": "var(--color-destructive)",
}


class DashboardView(OrganizationScopedView, TemplateView):
    """Unified transactional email dashboard for an organization."""

    template_name = "tx_email/dashboard.html"
    title = _("Email")
    parent = "accounts:org-home"

    def get_chart_data(self):
        """Return `(series, rows)` for a stacked line chart of recent messages."""
        return self.chart_data_for(OutgoingMessage)

    def get_incoming_chart_data(self):
        """Return `(series, rows)` for incoming mail, mirroring `get_chart_data`."""
        return self.chart_data_for(IncomingMessage)

    def chart_data_for(self, model):
        """Build `(series, rows)` for the given message model."""
        start = timezone.localdate() - timedelta(days=CHART_DAYS - 1)
        rows = (
            model.objects.filter(org=self.org, received_at__date__gte=start)
            .annotate(day=TruncDate("received_at"))
            .values("day", "status")
            .annotate(count=Count("id"))
        )
        counts = {}
        for row in rows:
            counts.setdefault(row["day"], {})[row["status"]] = row["count"]
        statuses = list(model.Status)
        series = [
            {
                "key": status.value,
                "label": str(status.label),
                "color": CHART_COLORS[status.value],
            }
            for status in statuses
        ]
        days = [start + timedelta(days=offset) for offset in range(CHART_DAYS)]
        return series, [
            {
                "day": day.isoformat(),
                **{
                    status.value: counts.get(day, {}).get(status.value, 0)
                    for status in statuses
                },
            }
            for day in days
        ]

    def get_context_data(self, **kwargs):
        out_series, out_rows = self.get_chart_data()
        in_series, in_rows = self.get_incoming_chart_data()
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "total_domains": Domain.objects.filter(org=self.org).count(),
            "total_messages": OutgoingMessage.objects.filter(org=self.org).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
            "outgoing_chart": {"series": out_series, "rows": out_rows},
            "incoming_chart": {"series": in_series, "rows": in_rows},
        }
