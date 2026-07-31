"""Unified transactional email views — merged messages and reports timelines."""

from django.db.models import Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, RedirectView

from accounts.views import OrganizationScopedView
from dmarc.models import DmarcFailureReport, DmarcReport
from mx.models import TlsReport

from .models import Message


class ContactMessagesView(OrganizationScopedView, ListView):
    """Unified timeline of inbound and outbound messages for the current org."""

    template_name = "tx_mail/contact_messages.html"
    context_object_name = "messages"
    paginate_by = 50
    title = _("Messages")
    parent = "accounts:org-home"

    class Direction:
        ALL = "all"
        SENT = "sent"
        RECEIVED = "received"

        CHOICES = (ALL, SENT, RECEIVED)

    def get_queryset(self):
        qs = Message.objects.filter(org=self.org).select_related(
            "outgoingmessage",
            "incomingmessage",
        )
        direction = self.request.GET.get("direction", self.Direction.ALL)
        match direction:
            case self.Direction.SENT:
                qs = qs.filter(kind=Message.Kind.OUTGOING)
            case self.Direction.RECEIVED:
                qs = qs.filter(kind=Message.Kind.INCOMING)
        if email := self.request.GET.get("email"):
            qs = qs.filter(Q(mail_from__icontains=email) | Q(rcpt_to__icontains=email))
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "direction": self.request.GET.get("direction", self.Direction.ALL),
            "email": self.request.GET.get("email", ""),
        }


class ContactReportsView(OrganizationScopedView, ListView):
    """Unified timeline of DMARC and TLS reports for the current org."""

    template_name = "tx_mail/contact_reports.html"
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


class MergedMessagesRedirectView(OrganizationScopedView, RedirectView):
    """Redirect legacy message-list URLs to the merged Messages view.

    Subclasses set ``direction`` to one of "sent" or "received" to scope
    the merged view to a particular direction. Inherits from
    ``OrganizationScopedView`` so non-members are 404'd before the
    redirect happens, and anonymous users are redirected to login.
    """

    permanent = False
    query_string = True

    direction: str = "all"

    def get_redirect_url(self, *args, **kwargs):
        url = reverse("tx_mail:contact-messages", kwargs={"org_slug": self.org.slug})
        return f"{url}?direction={self.direction}"


class MergedReportsRedirectView(OrganizationScopedView, RedirectView):
    """Redirect legacy report-list URLs to the merged Reports view.

    Subclasses set ``report_type`` to one of "dmarc", "failures", or "tls".
    """

    permanent = False
    query_string = True

    report_type: str = "dmarc"

    def get_redirect_url(self, *args, **kwargs):
        url = reverse("tx_mail:contact-reports", kwargs={"org_slug": self.org.slug})
        return f"{url}?type={self.report_type}"
