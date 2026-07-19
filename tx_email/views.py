"""Transactional email — unified dashboard."""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from domains.models import Domain
from smtp.models import OutgoingMessage


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "tx_email/dashboard.html"

    def get_context_data(self, **kwargs):
        orgs = self.request.user.organizations.all()
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org__in=orgs),
            "total_domains": Domain.objects.filter(org__in=orgs).count(),
            "total_messages": OutgoingMessage.objects.filter(
                sender=self.request.user
            ).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
        }
