from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import generic
from django.views.decorators.csrf import csrf_exempt

from abstract.views import ConditionalGetMixin, NoStoreCacheMixin
from accounts.models import Organization
from accounts.views import OrganizationScopedView
from domains.models import Domain

from .billing import month_cost, overage_price
from .charts import build_reputation_chart, build_volume_chart
from .models import DigestOptOut, FblReport


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


# A mail client posts one click with no session, so the signed token is the
# whole credential and CSRF middleware has nothing to check.
@method_decorator(csrf_exempt, name="dispatch")
class DigestOptOutView(NoStoreCacheMixin, generic.TemplateView):
    """
    Confirm and record one member's exit from the weekly digest.

    The link carries a signed token, so it works without signing in. A GET
    only shows the confirmation: prefetchers and scanners follow links, and
    none of them may stop a member's mail.
    """

    template_name = "reputation/digest_opt_out.html"

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        try:
            org_pk, user_pk = signing.loads(kwargs["token"], salt=DigestOptOut.salt())
        except signing.BadSignature as error:
            raise Http404 from error
        self.org = get_object_or_404(Organization, pk=org_pk)
        self.member = get_object_or_404(get_user_model(), pk=user_pk)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "org": self.org,
            "member": self.member,
        }

    def post(self, request, *args, **kwargs):
        DigestOptOut.objects.get_or_create(org=self.org, user=self.member)
        return self.render_to_response(self.get_context_data(opted_out=True))
