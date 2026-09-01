from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import ConditionalGetMixin, NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from domains.models import Domain

from .charts import build_reputation_chart
from .models import FblReport


class FblReportListView(OrganizationScopedView, NoStoreCacheMixin, generic.ListView):
    def get_template_names(self):
        return ["reputation/fbl_report_list.html"]

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


class FblReportDetailView(
    OrganizationScopedView, ConditionalGetMixin, generic.DetailView
):
    def get_template_names(self):
        return ["reputation/fbl_report_detail.html"]

    context_object_name = "report"
    parent = "email-dashboard:report-list"

    def get_queryset(self):
        return FblReport.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parsed = self.object.message.parsed_email()
        headers = list(parsed.items()) if parsed else []
        payload = parsed.get_payload(decode=True) if parsed else None
        body = (
            payload.decode(parsed.get_content_charset() or "utf-8", errors="replace")
            if isinstance(payload, bytes)
            else ""
        )
        return context | {
            "headers": headers,
            "body": body,
        }


class ReputationOverviewView(OrganizationScopedView, generic.TemplateView):
    def get_template_names(self):
        return ["reputation/overview.html"]

    title = _("Reputation")
    parent = "accounts:org-home"

    def get_context_data(self, **kwargs):
        chart = build_reputation_chart(self.org)
        last = chart["rows"][-1]
        stats = {
            "total_sent": last["sent"],
            "hard_bounces": last["hard_bounced"],
            "soft_bounces": last["soft_bounced"],
            "complaints": last["complained"],
            "hard_bounce_rate": last["hard_bounce_rate"] or 0.0,
            "complaint_rate": last["complaint_rate"] or 0.0,
        }
        chart_rates = {
            "series": chart["rate_series"],
            "rows": chart["rows"],
            "y_scale": {"stacked": "false"},
        }
        return super().get_context_data(**kwargs) | {
            "stats": stats,
            "chart": chart,
            "chart_rates": chart_rates,
            "bounce_threshold": settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD,
            "complaint_threshold": settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD,
            "min_volume": settings.RELAY_REPUTATION_MIN_VOLUME,
            "window_days": settings.RELAY_REPUTATION_WINDOW_DAYS,
        }
