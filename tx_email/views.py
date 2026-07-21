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
from smtp.models import OutgoingMessage

CHART_DAYS = 30
CHART_COLORS = {
    # Positive outcome: green.
    "delivered": "var(--color-success)",
    # In-flight: brand primary.
    "sent": "var(--color-primary)",
    "pending": "var(--color-muted-foreground)",
    # Transient problem: amber.
    "held": "var(--color-warning)",
    "bounced": "var(--color-warning)",
    # Terminal failure: red.
    "failed": "var(--color-destructive)",
    "dropped": "var(--color-destructive)",
}


class DashboardView(OrganizationScopedView, TemplateView):
    """Unified transactional email dashboard for an organization."""

    template_name = "tx_email/dashboard.html"
    title = _("Email")
    parent = "accounts:org-home"

    def get_chart_data(self):
        """Return `(series, rows)` for a stacked line chart of recent messages.

        `series` maps `OutgoingMessage.Status` values to chart series config.
        `rows` is a list of per-day dicts keyed by status, in chronological
        order, suitable for direct serialization into a basecoat `data` array.
        """
        start = timezone.localdate() - timedelta(days=CHART_DAYS - 1)
        rows = (
            OutgoingMessage.objects.filter(org=self.org, received_at__date__gte=start)
            .annotate(day=TruncDate("received_at"))
            .values("day", "status")
            .annotate(count=Count("id"))
        )
        counts = {}
        for row in rows:
            counts.setdefault(row["day"], {})[row["status"]] = row["count"]
        statuses = list(OutgoingMessage.Status)
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
        series, rows = self.get_chart_data()
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "total_domains": Domain.objects.filter(org=self.org).count(),
            "total_messages": OutgoingMessage.objects.filter(org=self.org).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
            "chart": {"series": series, "rows": rows},
        }
