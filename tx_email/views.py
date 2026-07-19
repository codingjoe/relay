"""Provide the unified transactional email dashboard."""

from django.conf import settings
from django.views.generic import TemplateView

from accounts.views import OrganizationScopedView
from domains.models import Domain
from smtp.models import OutgoingMessage


class DashboardView(OrganizationScopedView, TemplateView):
    template_name = "tx_email/dashboard.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "total_domains": Domain.objects.filter(org=self.org).count(),
            "total_messages": OutgoingMessage.objects.filter(org=self.org).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
        }
