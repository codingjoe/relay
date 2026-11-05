from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from domains.models import Domain
from services.email.dmarc.charts import build_dmarc_chart
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.msa.submission import (
    get_credential_key_context,
    get_submission_context,
)
from services.email.mta.charts import build_tls_chart
from services.email.mta.models import TlsReport
from services.email.reputation.models import FblReport

from .charts import ReportType, build_report_chart
from .onboarding import get_email_context


class GetStartedView(OrganizationScopedView, NoStoreCacheMixin, generic.TemplateView):
    """Walk a new organization through the first sending steps."""

    template_name = "dashboard/get_started.html"
    title = _("Get started")
    parent = "accounts:org-home"

    def get(self, request, *args, **kwargs):
        if get_email_context(self.org, request)["onboarding_complete"]:
            return redirect("monitoring:overview", org_slug=self.org.slug)
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = get_email_context(self.org, self.request)
        return (
            super().get_context_data(**kwargs)
            | context
            | get_submission_context()
            | get_credential_key_context(self.request, self.org.slug)
        )


class ReportListView(OrganizationScopedView, NoStoreCacheMixin, generic.ListView):
    """Display a merged timeline of DMARC and TLS reports."""

    def get_template_names(self):
        return ["dashboard/report_list.html"]

    context_object_name = "reports"
    paginate_by = 50
    title = _("Reports")
    parent = "accounts:org-home"

    TYPE_ICONS = {
        ReportType.DMARC: "shield-check",
        ReportType.FAILURES: "alert-triangle",
        ReportType.TLS: "lock",
        ReportType.FBL: "flag",
    }

    def get_selected_types(self):
        """Return the valid report types named by the repeated `type` parameter."""
        valid = {choice.value for choice in ReportType}
        return list(
            dict.fromkeys(
                value for value in self.request.GET.getlist("type") if value in valid
            )
        )

    def get_selected_ip(self):
        """Return the active IP address filter."""
        return self.request.GET.get("ip", "")

    def get_selected_domain(self):
        """Return the active domain filter."""
        return self.request.GET.get("domain", "")

    def get_type_queryset(self, choice, ip, domain):
        """Return the queryset for one report type with the active filters."""
        match choice:
            case ReportType.DMARC:
                qs = DmarcReport.objects.filter(org=self.org).select_related("domain")
                if ip:
                    qs = qs.filter(records__source_ip_address=ip).distinct()
            case ReportType.FAILURES:
                qs = DmarcFailureReport.objects.filter(org=self.org).select_related(
                    "domain"
                )
                if ip:
                    qs = qs.filter(source_ip_address=ip)
            case ReportType.TLS:
                qs = TlsReport.objects.filter(org=self.org).select_related("domain")
                if ip:
                    qs = qs.filter(failures__sending_mta_ip_address=ip).distinct()
            case ReportType.FBL:
                qs = FblReport.objects.filter(org=self.org).select_related("domain")
                if ip:
                    qs = qs.filter(source_ip_address=ip)
        if domain:
            qs = qs.filter(domain__name=domain)
        return qs

    def annotate_report(self, report, choice):
        """Attach the per-row display values of one report type."""
        report.report_type_label = choice.label
        report.report_icon = self.TYPE_ICONS[choice]
        match choice:
            case ReportType.TLS:
                report.report_subtitle = report.reporting_email
            case ReportType.FBL:
                report.report_subtitle = report.original_mail_from
            case _:
                report.report_subtitle = report.mail_from

    def get_queryset(self):
        selected = self.get_selected_types() or [choice.value for choice in ReportType]
        ip = self.get_selected_ip()
        domain = self.get_selected_domain()
        reports = []
        for choice in (ReportType(selected_type) for selected_type in selected):
            qs = self.get_type_queryset(choice, ip, domain)
            for report in qs:
                self.annotate_report(report, choice)
            reports.extend(qs)
        return sorted(reports, key=lambda report: report.created_at, reverse=True)

    def get_chart(self, selected):
        """Return the title and chart for the selected report types, or none."""
        if len(selected) == 1:
            match selected[0]:
                case ReportType.DMARC:
                    return _("messages by DMARC verdict"), build_dmarc_chart(self.org)
                case ReportType.TLS:
                    return _("failures by type"), build_tls_chart(self.org)
                case _:
                    return None, None
        report_types = [ReportType(value) for value in selected] or list(ReportType)
        return _("volume by report type"), build_report_chart(self.org, report_types)

    def get_type_label(self, selected):
        """Return the trigger label for the selected report types."""
        if not selected or len(selected) == len(ReportType):
            return _("all reports")
        return ", ".join(str(ReportType(value).label) for value in selected)

    def get_type_options(self, selected):
        """Return one toggle link per report type."""
        query = self.request.GET.copy()
        query.pop("page", None)
        query.pop("type", None)
        options = []
        for choice in ReportType:
            values = [value for value in selected if value != choice.value]
            if choice.value not in selected:
                values.append(choice.value)
            params = query.copy()
            if values:
                params.setlist("type", values)
            options.append(
                {
                    "value": choice.value,
                    "label": choice.label,
                    "icon": self.TYPE_ICONS[choice],
                    "checked": choice.value in selected,
                    "href": f"?{params.urlencode()}",
                }
            )
        return options

    def get_context_data(self, **kwargs):
        selected = self.get_selected_types()
        ip = self.get_selected_ip()
        domain = self.get_selected_domain()
        chart_title, chart = self.get_chart(selected)
        return super().get_context_data(**kwargs) | {
            "types": selected,
            "type_label": self.get_type_label(selected),
            "type_options": self.get_type_options(selected),
            "domain": domain,
            "domains": Domain.objects.filter(org=self.org).order_by("name"),
            "ip": ip,
            "chart_title": chart_title,
            "chart": chart,
        }
