import json
import logging

import authres
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import ConditionalGetMixin, NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from domains.models import Domain
from kms.models import SigningKey
from services.email.message.views import MessageBreadcrumbMixin

from .charts import build_tls_chart
from .forms import WebhookForm
from .models import IncomingMessage, TlsReport, Webhook, WebhookDelivery
from .tasks import deliver_to_webhook

logger = logging.getLogger(__name__)

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

# The headers an ARC set consists of (RFC 8617 §2).
ARC_HEADER_NAMES = frozenset(
    {"arc-seal", "arc-message-signature", "arc-authentication-results"}
)

RESULT_BADGE_VARIANTS = {
    "pass": "success",
    "fail": "destructive",
    "softfail": "destructive",
    "reject": "destructive",
    "quarantine": "destructive",
}


def authentication_results(headers, message):
    """
    Return parsed Authentication-Results headers for the detail page.

    Each entry carries the evaluating authserv-id, per-method verdicts
    with a badge variant, whether relay itself produced the evaluation,
    and the raw header for the verbatim view.
    """
    results = []
    for key, value in headers:
        match key.lower():
            case "authentication-results":
                try:
                    header = authres.AuthenticationResultsHeader.parse(
                        f"{key}: {value}"
                    )
                except authres.AuthResError, UnicodeDecodeError:
                    logger.warning(
                        "Unparseable Authentication-Results header", exc_info=True
                    )
                    header = None
                if header is None:
                    results.append(
                        {
                            "authserv_id": "",
                            "verdicts": [],
                            "is_relay": False,
                            "raw": f"{key}: {value}",
                        }
                    )
                else:
                    results.append(
                        {
                            "authserv_id": header.authserv_id or "",
                            "verdicts": [
                                {
                                    "method": result.method,
                                    "result": result.result,
                                    "variant": RESULT_BADGE_VARIANTS.get(
                                        result.result, "outline"
                                    ),
                                }
                                for result in header.results
                            ],
                            "is_relay": (
                                bool(header.authserv_id)
                                and message.domain_id is not None
                                and header.authserv_id == message.domain.sender_domain
                            ),
                            "raw": f"{key}: {value}",
                        }
                    )
    return results


class IncomingMessageDetailView(
    OrganizationScopedView,
    ConditionalGetMixin,
    MessageBreadcrumbMixin,
    generic.DetailView,
):
    context_object_name = "message"
    parent = "message:message-list"

    def get_queryset(self):
        return IncomingMessage.objects.filter(org=self.org).select_related(
            "org", "content_type", "tls_certificate"
        )

    def get_object(self, queryset=None):
        return get_object_or_404(queryset or self.get_queryset(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        message = self.object
        headers = message.parsed_headers
        is_report = message.content_type.model_class() is not IncomingMessage
        return context | {
            "headers": headers,
            "body": message.text_body,
            "authentication_results": authentication_results(headers, message),
            "arc_headers": [
                [key, value]
                for key, value in headers
                if key.lower() in ARC_HEADER_NAMES
            ],
            "webhook_deliveries": WebhookDelivery.objects.filter(
                message=message
            ).select_related("webhook__signing_key"),
            "is_report": is_report,
            "report_url": message.get_absolute_url() if is_report else "",
            "report_kind": message.kind_display if is_report else "",
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


class TlsReportListView(OrganizationScopedView, NoStoreCacheMixin, generic.ListView):
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


class TlsReportDetailView(
    OrganizationScopedView, ConditionalGetMixin, generic.DetailView
):
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
