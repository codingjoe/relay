"""Message log and detail views."""

from email import message_from_bytes

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, View

from .models import Message, Transmission


class MessageLogView(LoginRequiredMixin, ListView):
    template_name = "message_log.html"
    context_object_name = "messages"
    paginate_by = 50

    def get_queryset(self):
        qs = Message.objects.filter(sender=self.request.user).select_related("domain")
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(domain_id=domain)
        if scope := self.request.GET.get("scope"):
            qs = qs.filter(scope=scope)
        if status := self.request.GET.get("status"):
            qs = qs.filter(status=status)
        if search := self.request.GET.get("search"):
            qs = qs.filter(rcpt_to__icontains=search)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": self.request.user.domains.all(),
            "status_choices": Message.Status.choices,
            "filters": {
                "domain": self.request.GET.get("domain", ""),
                "scope": self.request.GET.get("scope", ""),
                "status": self.request.GET.get("status", ""),
                "search": self.request.GET.get("search", ""),
            },
        }


class MessageDetailView(LoginRequiredMixin, DetailView):
    template_name = "message_detail.html"
    context_object_name = "message"

    def get_queryset(self):
        return Message.objects.filter(sender=self.request.user).select_related(
            "domain", "credential"
        )

    def get_object(self, queryset=None):
        return get_object_or_404(queryset or self.get_queryset(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        message = self.object
        raw_bytes = message.raw_body.read()
        parsed = message_from_bytes(raw_bytes)
        headers = list(parsed.items())
        dkim_signatures = [
            dict(
                s.strip().split("=", 1)
                for field in value.split(";")
                if (s := field.strip())
            )
            for k, value in headers
            if k.lower() == "dkim-signature"
        ]
        received = [v for k, v in headers if k.lower() == "received"]
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
            "dkim_signatures": dkim_signatures,
            "received": received,
            "parts": parts,
            "transmissions": Transmission.objects.filter(message=message),
        }


class MessageModalView(LoginRequiredMixin, View):
    def get(self, request, pk, *args, **kwargs):
        message = get_object_or_404(
            Message.objects.filter(sender=request.user).select_related("domain"),
            pk=pk,
        )
        transmissions = Transmission.objects.filter(message=message).values(
            "status",
            "code",
            "created_at",
            "sent_with_ssl",
            "log_id",
            "output",
            "details",
        )
        return JsonResponse(
            {
                "id": str(message.id),
                "mail_from": message.mail_from,
                "rcpt_to": message.rcpt_to,
                "subject": message.subject,
                "scope": message.get_scope_display(),
                "status": message.get_status_display(),
                "received_at": message.received_at.isoformat(),
                "size": message.size,
                "message_id": message.message_id,
                "domain": message.domain.name if message.domain else None,
                "tag": message.tag,
                "detail_url": reverse_lazy(
                    "mail:message_detail", kwargs={"pk": message.id}
                ),
                "transmissions": list(transmissions),
            }
        )
