import json

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic

from accounts.views import OrganizationScopedView
from domains.models import Domain
from kms.models import SigningKey

from .charts import build_tls_chart
from .forms import WebhookForm
from .models import IncomingMessage, TlsReport, Webhook, WebhookDelivery
from .tasks import deliver_to_webhook

# Sample payload rendered as highlighted JSON on the webhook list page.
WEBHOOK_PAYLOAD = {
    "type": "email.received",
    "message_id": "0192...",
    "sender": "sender@example.com",
    "recipient": "recipient@app.acme.com",
    "subject": "Hello",
    "rfc822_message_id": "<abc@example.com>",
    "received_with_tls": True,
    "receiving_domain": "app.acme.com",
    "body_url": "https://bucket.s3.amazonaws.com/messages/uuid.eml?...",
    "received_at": "2026-07-27T18:58:09Z",
}


class IncomingMessageDetailView(OrganizationScopedView, generic.DetailView):
    context_object_name = "message"
    parent = "message:message-list"

    def get_queryset(self):
        return IncomingMessage.objects.filter(org=self.org)

    def get_object(self, queryset=None):
        return get_object_or_404(queryset or self.get_queryset(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        parsed = self.object.parsed_email()
        return context | {
            "headers": self.object.parsed_headers,
            "parts": list(parsed.walk()) if parsed.is_multipart() else [parsed],
            "body": parsed.get_payload(decode=True) or "",
            "webhook_deliveries": WebhookDelivery.objects.filter(
                message=self.object
            ).select_related("webhook"),
        }


class WebhookListView(OrganizationScopedView, generic.ListView):
    context_object_name = "webhooks"
    title = _("Webhooks")
    parent = "email-dashboard:dashboard"

    def get_queryset(self):
        return Webhook.objects.filter(org=self.org).select_related("signing_key")

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domain_choices": Domain.objects.filter(org=self.org),
            "webhook_payload": json.dumps(WEBHOOK_PAYLOAD, indent=2),
        }


class WebhookCreateView(OrganizationScopedView, generic.CreateView):
    http_method_names = ["post"]
    model = Webhook
    form_class = WebhookForm
    title = _("New webhook")
    parent = "mta:webhook-list"

    def get_form_kwargs(self):
        return super().get_form_kwargs() | {"org": self.org}

    def form_valid(self, form):
        with transaction.atomic():
            webhook = form.save(commit=False)
            webhook.org = self.org
            webhook.signing_key = SigningKey.generate(SigningKey.Algorithm.ED25519)
            webhook.save(force_insert=True)
            self.object = webhook
        messages.success(self.request, _("Created webhook."))
        return redirect(self.get_success_url())

    def form_invalid(self, form):
        for errors in form.errors.values():
            for error in errors:
                messages.error(self.request, error)
        return redirect("mta:webhook-list", org_slug=self.org.slug)

    def get_success_url(self):
        return reverse_lazy("mta:webhook-list", kwargs={"org_slug": self.org.slug})


class WebhookDeleteView(OrganizationScopedView, generic.DeleteView):
    model = Webhook
    title = _("Delete")
    parent = "mta:webhook-list"

    def get_queryset(self):
        return Webhook.objects.filter(org=self.org)

    def get_success_url(self):
        return reverse_lazy("mta:webhook-list", kwargs={"org_slug": self.org.slug})

    def form_valid(self, form):
        messages.success(self.request, _("Deleted webhook."))
        return super().form_valid(form)


class WebhookTestView(OrganizationScopedView, generic.View):
    def post(self, request, org_slug, pk, *args, **kwargs):
        webhook = get_object_or_404(Webhook, pk=pk, org=self.org)
        ok, _status = deliver_to_webhook(message=None, webhook=webhook, is_test=True)
        if ok:
            messages.success(request, _("Delivered test webhook."))
        else:
            messages.error(request, _("Test webhook failed."))
        return redirect("mta:webhook-list", org_slug=org_slug)


class TlsReportListView(OrganizationScopedView, generic.ListView):
    def get_template_names(self):
        return ["mta/tls_report_list.html"]

    context_object_name = "reports"
    paginate_by = 50
    title = _("TLS reports")
    parent = "email-dashboard:dashboard"

    def get_queryset(self):
        qs = TlsReport.objects.filter(org=self.org).select_related("domain")
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(domain__name=domain)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "filters": {
                "domain": self.request.GET.get("domain", ""),
            },
            "chart": build_tls_chart(self.org),
        }


class TlsReportDetailView(OrganizationScopedView, generic.DetailView):
    def get_template_names(self):
        return ["mta/tls_report_detail.html"]

    context_object_name = "report"
    parent = "email-dashboard:report-list"

    def get_queryset(self):
        return TlsReport.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "failures": self.object.failures.all(),
        }
