"""DMARC report views."""

from django.utils.translation import gettext_lazy as _
from django.views.generic import DetailView, ListView

from accounts.views import OrganizationScopedView
from domains.models import Domain

from .charts import build_dmarc_chart
from .models import DmarcFailureReport, DmarcReport


class DmarcReportListView(OrganizationScopedView, ListView):
    template_name = "dmarc/report_list.html"
    context_object_name = "reports"
    paginate_by = 50
    title = _("DMARC reports")
    parent = "tx_email:dashboard"

    def get_queryset(self):
        qs = DmarcReport.objects.filter(org=self.org)
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(domain__name=domain)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "filters": {
                "domain": self.request.GET.get("domain", ""),
            },
            "chart": build_dmarc_chart(self.org),
        }


class DmarcReportDetailView(OrganizationScopedView, DetailView):
    template_name = "dmarc/report_detail.html"
    context_object_name = "report"
    parent = "dmarc:report-list"

    def get_queryset(self):
        return DmarcReport.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "records": self.object.records.select_related("report"),
        }


class DmarcFailureReportListView(OrganizationScopedView, ListView):
    template_name = "dmarc/failure_report_list.html"
    context_object_name = "reports"
    paginate_by = 50
    title = _("DMARC failure reports")
    parent = "tx_email:dashboard"

    def get_queryset(self):
        qs = DmarcFailureReport.objects.filter(org=self.org)
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(domain__name=domain)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "filters": {
                "domain": self.request.GET.get("domain", ""),
            },
        }


class DmarcFailureReportDetailView(OrganizationScopedView, DetailView):
    template_name = "dmarc/failure_report_detail.html"
    context_object_name = "report"
    parent = "dmarc:failure-report-list"

    def get_queryset(self):
        return DmarcFailureReport.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "incoming_message": self.object.incoming_message,
        }
