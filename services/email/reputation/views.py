from django.conf import settings
from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import ConditionalGetMixin, NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from domains.models import Domain

from . import svg
from .billing import month_cost, overage_price
from .charts import build_reputation_chart, build_volume_chart
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

    title = _("Monitoring")
    parent = "accounts:org-home"

    def get_context_data(self, **kwargs):
        chart = build_reputation_chart(self.org)
        volume = build_volume_chart(self.org)
        cost = month_cost(volume["this_month_total"])
        last = chart["rows"][-1]
        bounce_threshold = settings.RELAY_REPUTATION_BOUNCE_RATE_THRESHOLD
        complaint_threshold = settings.RELAY_REPUTATION_COMPLAINT_RATE_THRESHOLD
        # The chart carries rates in per cent; the cards format fractions.
        hard_bounce_rate = (last["hard_bounce_rate"] or 0.0) / 100
        complaint_rate = (last["complaint_rate"] or 0.0) / 100
        stats = {
            "hard_bounce_rate": hard_bounce_rate,
            "complaint_rate": complaint_rate,
            "hard_bounce_over_limit": hard_bounce_rate > bounce_threshold,
            "complaint_over_limit": complaint_rate > complaint_threshold,
        }
        return super().get_context_data(**kwargs) | {
            "stats": stats,
            "chart_bounces": chart["bounce_chart"],
            "chart_complaints": chart["complaint_chart"],
            "chart_volume": volume,
            "cost": cost,
            "month_messages": volume["this_month_total"],
            "overage_price": overage_price(),
            "free_monthly_messages": settings.RELAY_FREE_MONTHLY_MESSAGES,
            "bounce_threshold": bounce_threshold,
            "complaint_threshold": complaint_threshold,
        }


def chart_number(value: str, default: float = 0.0) -> float:
    """Return the number a chart query string carries, or the default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class DigestChartView(generic.View):
    """Draw one chart of the digest mail from the numbers in its query."""

    kind = "bar"

    def get(self, request, *args, **kwargs):
        response = HttpResponse(
            self.get_svg(request.GET),
            content_type="image/svg+xml",
        )
        response["Cache-Control"] = "public, max-age=604800, immutable"
        response["X-Content-Type-Options"] = "nosniff"
        return response

    def get_svg(self, query):
        match self.kind:
            case "week":
                counts = [
                    max(int(chart_number(part)), 0)
                    for part in query.get("counts", "").split(",")
                    if part
                ]
                return svg.week(counts[:31], tone=query.get("tone", "primary"))
            case _:
                height = int(chart_number(query.get("height"), 12))
                return svg.bar(
                    chart_number(query.get("value")),
                    tone=query.get("tone", "good"),
                    height=min(max(height, 6), 24),
                    marker=query.get("marker") == "1",
                )
