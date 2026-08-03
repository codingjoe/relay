"""Provide the unified transactional email dashboard and chart API."""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, TemplateView
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response

from abstract.serializers import ChartDataSerializer
from accounts.views import OrganizationScopedView
from domains.models import Domain
from services.email.dmarc.charts import build_dmarc_chart
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.message.models import Message
from services.email.mx.charts import build_incoming_chart, build_tls_chart
from services.email.mx.models import TlsReport
from services.email.smtp.charts import build_outgoing_chart


class DashboardView(OrganizationScopedView, TemplateView):
    """Unified transactional email dashboard for an organization."""

    template_name = "dashboard/dashboard.html"
    title = _("Email")
    parent = "accounts:org-home"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "total_domains": Domain.objects.filter(org=self.org).count(),
            "total_messages": Message.objects.filter(org=self.org).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
            "outgoing_chart": build_outgoing_chart(self.org),
            "incoming_chart": build_incoming_chart(self.org),
            "dmarc_chart": build_dmarc_chart(self.org),
            "tls_chart": build_tls_chart(self.org),
        }


class ChartDataView(OrganizationScopedView, RetrieveAPIView):
    """API endpoint returning chart data as JSON for interactive charts."""

    serializer_class = ChartDataSerializer

    CHART_BUILDERS = {
        "outgoing": build_outgoing_chart,
        "incoming": build_incoming_chart,
        "dmarc": build_dmarc_chart,
        "tls": build_tls_chart,
    }

    def retrieve(self, request, *args, **kwargs):
        chart_type = kwargs["chart_type"]
        builder = self.CHART_BUILDERS[chart_type]
        data = builder(self.org)
        serializer = self.get_serializer(data)
        return Response(serializer.data)


class ReportListView(OrganizationScopedView, ListView):
    """Merged timeline of DMARC and TLS reports."""

    template_name = "dashboard/report_list.html"
    context_object_name = "reports"
    paginate_by = 50
    title = _("Reports")
    parent = "accounts:org-home"

    class ReportType:
        DMARC = "dmarc"
        FAILURES = "failures"
        TLS = "tls"

        CHOICES = (DMARC, FAILURES, TLS)

    def get_queryset(self):
        report_type = self.request.GET.get("type", self.ReportType.DMARC)
        domain = self.request.GET.get("domain", "")
        ip = self.request.GET.get("ip", "")
        match report_type:
            case self.ReportType.DMARC:
                qs = DmarcReport.objects.filter(org=self.org)
                if ip:
                    qs = qs.filter(source_ip_address=ip)
            case self.ReportType.FAILURES:
                qs = DmarcFailureReport.objects.filter(org=self.org)
                if ip:
                    qs = qs.filter(source_ip_address=ip)
            case self.ReportType.TLS:
                qs = TlsReport.objects.filter(org=self.org).select_related("domain")
                if domain:
                    qs = qs.filter(domain__name=domain)
            case _:
                qs = DmarcReport.objects.filter(org=self.org)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "type": self.request.GET.get("type", self.ReportType.DMARC),
            "domain": self.request.GET.get("domain", ""),
            "ip": self.request.GET.get("ip", ""),
        }
