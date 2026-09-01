from django.db import models
from django.utils.translation import gettext_lazy as _
from django.views import generic
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response

from abstract.serializers import ChartDataSerializer
from accounts.views import OrganizationScopedView
from domains.models import Domain
from services.email.dmarc.charts import build_dmarc_chart
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.message.models import Message
from services.email.msa.charts import build_outgoing_chart
from services.email.msa.models import OutgoingMessage
from services.email.mta.charts import build_incoming_chart, build_tls_chart
from services.email.mta.models import TlsReport
from services.email.reputation.charts import build_reputation_chart
from services.email.reputation.models import FblReport


class DashboardView(OrganizationScopedView, generic.TemplateView):
    """Display the unified transactional email dashboard for an organization."""

    template_name = "dashboard/dashboard.html"
    title = _("Email")
    parent = "accounts:org-home"

    def get_context_data(self, **kwargs):
        domains = list(Domain.objects.filter(org=self.org))
        return super().get_context_data(**kwargs) | {
            "domains": domains,
            "total_domains": len(domains),
            "total_messages": Message.objects.filter(org=self.org).count(),
            "managed_domain": next(
                (
                    domain
                    for domain in domains
                    if domain.is_managed and domain.verified_at
                ),
                None,
            ),
            "has_custom_domain": any(not domain.is_managed for domain in domains),
            "has_outgoing_message": OutgoingMessage.objects.filter(
                org=self.org
            ).exists(),
            "outgoing_chart": build_outgoing_chart(self.org),
            "incoming_chart": build_incoming_chart(self.org),
            "dmarc_chart": build_dmarc_chart(self.org),
            "tls_chart": build_tls_chart(self.org),
            "reputation_chart": build_reputation_chart(self.org),
        }


class ChartDataView(OrganizationScopedView, RetrieveAPIView):
    """Return chart data as JSON for interactive charts."""

    serializer_class = ChartDataSerializer

    CHART_BUILDERS = {
        "outgoing": build_outgoing_chart,
        "incoming": build_incoming_chart,
        "dmarc": build_dmarc_chart,
        "tls": build_tls_chart,
        "reputation": build_reputation_chart,
    }

    def retrieve(self, request, *args, **kwargs):
        chart_type = kwargs["chart_type"]
        builder = self.CHART_BUILDERS[chart_type]
        data = builder(self.org)
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class ReportListView(OrganizationScopedView, generic.ListView):
    """Display a merged timeline of DMARC and TLS reports."""

    def get_template_names(self):
        return ["dashboard/report_list.html"]

    context_object_name = "reports"
    paginate_by = 50
    title = _("Reports")
    parent = "accounts:org-home"

    class ReportType(models.TextChoices):
        DMARC = "dmarc", _("DMARC")
        FAILURES = "failures", _("DMARC failures")
        TLS = "tls", _("TLS")
        FBL = "fbl", _("FBL")

    def get_queryset(self):
        report_type = self.request.GET.get("type", self.ReportType.DMARC)
        domain = self.request.GET.get("domain", "")
        ip = self.request.GET.get("ip", "")
        match report_type:
            case self.ReportType.DMARC:
                qs = DmarcReport.objects.filter(org=self.org).select_related("domain")
                if ip:
                    qs = qs.filter(records__source_ip_address=ip)
            case self.ReportType.FAILURES:
                qs = DmarcFailureReport.objects.filter(org=self.org).select_related(
                    "domain"
                )
                if ip:
                    qs = qs.filter(source_ip_address=ip)
            case self.ReportType.TLS:
                qs = TlsReport.objects.filter(org=self.org).select_related("domain")
                if domain:
                    qs = qs.filter(domain__name=domain)
            case self.ReportType.FBL:
                qs = FblReport.objects.filter(org=self.org)
                if domain:
                    qs = qs.filter(domain__name=domain)
                if ip:
                    qs = qs.filter(source_ip_address=ip)
            case _:
                qs = DmarcReport.objects.filter(org=self.org).select_related("domain")
        return qs

    def get_context_data(self, **kwargs):
        report_type = self.request.GET.get("type", self.ReportType.DMARC)
        domain = self.request.GET.get("domain", "")
        ip = self.request.GET.get("ip", "")
        filter_count = (
            int(report_type != self.ReportType.DMARC) + bool(domain) + bool(ip)
        )
        try:
            type_label = self.ReportType(report_type).label
        except ValueError:
            type_label = self.ReportType.DMARC.label
        return super().get_context_data(**kwargs) | {
            "type": report_type,
            "domain": domain,
            "ip": ip,
            "filter_count": filter_count,
            "type_label": type_label,
        }
