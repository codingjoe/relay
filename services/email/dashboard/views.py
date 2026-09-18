from django.db import models
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from services.email.dmarc.charts import build_dmarc_chart
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.mta.charts import build_tls_chart
from services.email.mta.models import TlsReport
from services.email.reputation.models import FblReport

from .onboarding import get_email_context


class GetStartedView(OrganizationScopedView, NoStoreCacheMixin, generic.TemplateView):
    """Walk a new organization through the first sending steps."""

    template_name = "dashboard/get_started.html"
    title = _("Get started")
    parent = "accounts:org-home"

    def get(self, request, *args, **kwargs):
        if get_email_context(self.org, request)["onboarding_complete"]:
            return redirect("reputation:overview", org_slug=self.org.slug)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | get_email_context(
            self.org, self.request
        )


class ReportListView(OrganizationScopedView, NoStoreCacheMixin, generic.ListView):
    """Display a merged timeline of DMARC and TLS reports."""

    def get_template_names(self):
        return ["dashboard/report_list.html"]

    context_object_name = "reports"
    paginate_by = 50
    title = _("Recipient reports")
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

    def get_chart(self, report_type):
        """Return the chart of the open report type, or None when it has none."""
        match report_type:
            case self.ReportType.DMARC:
                return build_dmarc_chart(self.org)
            case self.ReportType.TLS:
                return build_tls_chart(self.org)
            case _:
                return None

    def get_context_data(self, **kwargs):
        report_type = self.request.GET.get("type", self.ReportType.DMARC)
        domain = self.request.GET.get("domain", "")
        ip = self.request.GET.get("ip", "")
        try:
            type_label = self.ReportType(report_type).label
        except ValueError:
            type_label = self.ReportType.DMARC.label
        return super().get_context_data(**kwargs) | {
            "type": report_type,
            "domain": domain,
            "ip": ip,
            "type_label": type_label,
            "filter_values": [value for value in (domain, ip) if value],
            "chart": self.get_chart(report_type),
        }
