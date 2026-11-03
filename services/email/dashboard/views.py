from django.db import models
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from services.email.dmarc.charts import build_dmarc_chart
from services.email.dmarc.models import DmarcFailureReport, DmarcReport
from services.email.msa.submission import (
    get_credential_key_context,
    get_submission_context,
)
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
    title = _("Recipient reports")
    parent = "accounts:org-home"

    class ReportType(models.TextChoices):
        DMARC = "dmarc", _("DMARC")
        FAILURES = "failures", _("DMARC failures")
        TLS = "tls", _("TLS")
        FBL = "fbl", _("FBL")

    TYPE_ICONS = {
        ReportType.DMARC: "shield-check",
        ReportType.FAILURES: "alert-triangle",
        ReportType.TLS: "lock",
        ReportType.FBL: "flag",
    }

    def get_selected_types(self):
        """Return the valid report types named by the repeated `type` parameter."""
        valid = {choice.value for choice in self.ReportType}
        return [value for value in self.request.GET.getlist("type") if value in valid]

    def get_search(self):
        """Return the active search parameter and its value."""
        if ip := self.request.GET.get("ip"):
            return "ip", ip
        if domain := self.request.GET.get("domain"):
            return "domain", domain
        return "ip", ""

    def get_type_queryset(self, choice, field, value):
        """Return the queryset for one report type with the active filter."""
        match choice:
            case self.ReportType.DMARC:
                qs = DmarcReport.objects.filter(org=self.org).select_related("domain")
                if field == "ip" and value:
                    qs = qs.filter(records__source_ip_address=value).distinct()
            case self.ReportType.FAILURES:
                qs = DmarcFailureReport.objects.filter(org=self.org).select_related(
                    "domain"
                )
                if field == "ip" and value:
                    qs = qs.filter(source_ip_address=value)
            case self.ReportType.TLS:
                qs = TlsReport.objects.filter(org=self.org).select_related("domain")
                if field == "ip" and value:
                    qs = qs.filter(failures__sending_mta_ip_address=value).distinct()
            case self.ReportType.FBL:
                qs = FblReport.objects.filter(org=self.org).select_related("domain")
                if field == "ip" and value:
                    qs = qs.filter(source_ip_address=value)
        if field == "domain" and value:
            qs = qs.filter(domain__name=value)
        return qs

    def annotate_report(self, report, choice):
        """Attach the per-row display values of one report type."""
        report.report_type_label = choice.label
        report.report_icon = self.TYPE_ICONS[choice]
        match choice:
            case self.ReportType.TLS:
                report.report_subtitle = report.reporting_email
            case self.ReportType.FBL:
                report.report_subtitle = report.original_mail_from
            case _:
                report.report_subtitle = report.mail_from

    def get_queryset(self):
        selected = self.get_selected_types() or [
            choice.value for choice in self.ReportType
        ]
        field, value = self.get_search()
        reports = []
        for choice in (self.ReportType(selected_type) for selected_type in selected):
            qs = self.get_type_queryset(choice, field, value)
            for report in qs:
                self.annotate_report(report, choice)
            reports.extend(qs)
        return sorted(reports, key=lambda report: report.created_at, reverse=True)

    def get_chart(self, selected):
        """Return the title and chart of a single selected report type, or none."""
        match selected:
            case [self.ReportType.DMARC]:
                return _("messages by DMARC verdict"), build_dmarc_chart(self.org)
            case [self.ReportType.TLS]:
                return _("failures by type"), build_tls_chart(self.org)
            case _:
                return None, None

    def get_type_label(self, selected):
        """Return the trigger label for the selected report types."""
        if not selected or len(selected) == len(self.ReportType):
            return _("all reports")
        return ", ".join(str(self.ReportType(value).label) for value in selected)

    def get_type_options(self, selected):
        """Return one toggle link per report type."""
        query = self.request.GET.copy()
        query.pop("page", None)
        query.pop("type", None)
        options = []
        for choice in self.ReportType:
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
        field, value = self.get_search()
        chart_title, chart = self.get_chart(selected)
        return super().get_context_data(**kwargs) | {
            "types": selected,
            "type_label": self.get_type_label(selected),
            "type_options": self.get_type_options(selected),
            "search_field": field,
            "search_value": value,
            "chart_title": chart_title,
            "chart": chart,
        }
