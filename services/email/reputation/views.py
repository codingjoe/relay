from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from accounts.views import OrganizationScopedView
from domains.models import Domain

from .charts import build_reputation_chart
from .models import FblReport
from .reputation import compute_domain_reputation


class FblReportListView(OrganizationScopedView, ListView):
    template_name = "reputation/fbl_report_list.html"
    context_object_name = "reports"
    paginate_by = 50
    title = _("FBL reports")
    parent = "email-dashboard:report-list"

    def get_queryset(self):
        qs = FblReport.objects.filter(org=self.org)
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(domain__name=domain)
        if feedback_type := self.request.GET.get("feedback_type"):
            qs = qs.filter(feedback_type=feedback_type)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "filters": {
                "domain": self.request.GET.get("domain", ""),
                "feedback_type": self.request.GET.get("feedback_type", ""),
            },
            "feedback_types": list(FblReport.FeedbackType),
        }


class FblReportDetailView(OrganizationScopedView, DetailView):
    template_name = "reputation/fbl_report_detail.html"
    context_object_name = "report"
    parent = "email-dashboard:report-list"

    def get_queryset(self):
        return FblReport.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parsed = self.object.parsed_email()
        headers = list(parsed.items())
        return context | {
            "headers": headers,
            "body": parsed.get_payload(decode=True) or "",
        }


class ReputationOverviewView(OrganizationScopedView, ListView):
    template_name = "reputation/overview.html"
    context_object_name = "domains"
    title = _("Reputation")
    parent = "accounts:org-home"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org, verified_at__isnull=False)

    def get_context_data(self, **kwargs):
        domains = list(self.get_queryset())
        domain_reputations = [
            (domain, compute_domain_reputation(domain)) for domain in domains
        ]
        return super().get_context_data(**kwargs) | {
            "domain_reputations": domain_reputations,
            "chart": build_reputation_chart(self.org),
            "bounce_threshold": settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD,
            "complaint_threshold": settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD,
        }
