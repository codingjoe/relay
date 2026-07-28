"""Provide the unified transactional email dashboard."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from accounts.views import OrganizationScopedView
from dmarc.charts import build_dmarc_chart
from domains.models import Domain
from mx.charts import build_incoming_chart, build_tls_chart
from smtp.charts import build_outgoing_chart
from smtp.models import OutgoingMessage


class DashboardView(OrganizationScopedView, TemplateView):
    """Unified transactional email dashboard for an organization."""

    template_name = "tx_email/dashboard.html"
    title = _("Email")
    parent = "accounts:org-home"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "total_domains": Domain.objects.filter(org=self.org).count(),
            "total_messages": OutgoingMessage.objects.filter(org=self.org).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
            "outgoing_chart": build_outgoing_chart(self.org),
            "incoming_chart": build_incoming_chart(self.org),
            "dmarc_chart": build_dmarc_chart(self.org),
            "tls_chart": build_tls_chart(self.org),
        }
