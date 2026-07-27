"""MX ingress views — inbox and webhook management."""

from email import message_from_bytes

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, DetailView, ListView, View

from accounts.views import OrganizationScopedView
from domains.models import Domain
from kms.models import SigningKey

from .charts import build_incoming_chart
from .models import IncomingMessage, Webhook, WebhookDelivery
from .tasks import deliver_to_webhook


class IncomingMessageListView(OrganizationScopedView, ListView):
    template_name = "mx/inbox.html"
    context_object_name = "messages"
    paginate_by = 50
    title = _("Inbox")
    parent = "tx_email:dashboard"

    def get_queryset(self):
        qs = IncomingMessage.objects.filter(org=self.org)
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(receiving_domain=domain)
        if search := self.request.GET.get("search"):
            qs = qs.filter(mail_from__icontains=search)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "receiving_domains": Domain.objects.filter(org=self.org),
            "chart": build_incoming_chart(self.org),
            "filters": {
                "domain": self.request.GET.get("domain", ""),
                "search": self.request.GET.get("search", ""),
            },
        }


class IncomingMessageDetailView(OrganizationScopedView, DetailView):
    template_name = "mx/message_detail.html"
    context_object_name = "message"
    parent = "mx:inbox"

    def get_queryset(self):
        return IncomingMessage.objects.filter(org=self.org)

    def get_object(self, queryset=None):
        return get_object_or_404(queryset or self.get_queryset(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        raw_bytes = self.object.raw_body.read()
        parsed = message_from_bytes(raw_bytes)
        headers = list(parsed.items())
        parts: list[dict] = []
        if parsed.is_multipart():
            for part in parsed.walk():
                if part.is_multipart():
                    continue
                charset = part.get_content_charset() or "utf-8"
                payload = part.get_payload(decode=True)
                parts.append(
                    {
                        "content_type": part.get_content_type(),
                        "body": payload.decode(charset, errors="replace")
                        if payload
                        else "",
                        "headers": list(part.items()),
                    }
                )
        else:
            charset = parsed.get_content_charset() or "utf-8"
            payload = parsed.get_payload(decode=True)
            parts.append(
                {
                    "content_type": parsed.get_content_type(),
                    "body": payload.decode(charset, errors="replace")
                    if payload
                    else parsed.get_payload(),
                    "headers": [],
                }
            )
        return context | {
            "headers": headers,
            "parts": parts,
            "webhook_deliveries": WebhookDelivery.objects.filter(
                message=self.object
            ).select_related("webhook"),
        }


class WebhookListView(OrganizationScopedView, ListView):
    template_name = "mx/webhook_list.html"
    context_object_name = "webhooks"
    title = _("Webhooks")
    parent = "tx_email:dashboard"

    def get_queryset(self):
        return Webhook.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        domain_choices = [(d.name, d.name) for d in Domain.objects.filter(org=self.org)]
        free_domain = settings.RELAY_FREE_SENDER_DOMAIN
        domain_choices.append((free_domain, f"{free_domain} ({_('free')})"))
        return super().get_context_data(**kwargs) | {
            "domain_choices": domain_choices,
        }


class WebhookCreateView(OrganizationScopedView, View):
    def post(self, request, org_slug, *args, **kwargs):
        url = request.POST.get("url", "")
        name = request.POST.get("name", "")
        pattern_prefix = request.POST.get("pattern_prefix", "*")
        domain_part = request.POST.get("domain_part", "") or request.POST.get(
            "domain", ""
        )
        address_pattern = f"{pattern_prefix}@{domain_part}"

        try:
            with transaction.atomic():
                signing_key = SigningKey.generate(SigningKey.Algorithm.ED25519)
                webhook = Webhook(
                    org=self.org,
                    url=url,
                    name=name,
                    address_pattern=address_pattern,
                    signing_key=signing_key,
                )
                webhook.full_clean()
                webhook.save(force_insert=True)
        except ValidationError as e:
            messages.error(request, "; ".join(e.messages))
        else:
            messages.success(request, _("Webhook created."))
        return redirect("mx:webhook-list", org_slug=org_slug)


class WebhookDeleteView(OrganizationScopedView, DeleteView):
    model = Webhook
    title = _("Delete")
    parent = "mx:webhook-list"

    def get_queryset(self):
        return Webhook.objects.filter(org=self.org)

    def get_success_url(self):
        return reverse_lazy("mx:webhook-list", kwargs={"org_slug": self.org.slug})

    def form_valid(self, form):
        messages.success(self.request, _("Webhook deleted."))
        return super().form_valid(form)


class WebhookTestView(OrganizationScopedView, View):
    def post(self, request, org_slug, pk, *args, **kwargs):
        webhook = get_object_or_404(Webhook, pk=pk, org=self.org)
        ok, _status = deliver_to_webhook(message=None, webhook=webhook, is_test=True)
        if ok:
            messages.success(request, _("Test webhook delivered."))
        else:
            messages.error(request, _("Test webhook failed."))
        return redirect("mx:webhook-list", org_slug=org_slug)
