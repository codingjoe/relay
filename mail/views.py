"""Message log and detail views."""

from email import message_from_bytes
from email.message import EmailMessage

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, View

from accounts.models import user_organizations
from domains.models import Domain

from .models import Message, Transmission
from .tasks import deliver_message


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
            "domains": Domain.objects.filter(
                organization__in=user_organizations(self.request.user)
            ),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
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
            Message.objects.filter(sender=request.user).select_related(
                "domain", "credential"
            ),
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
                "credential": message.credential.key_prefix
                if message.credential
                else None,
                "credential_type": (
                    message.credential.get_type_display()
                    if message.credential
                    else None
                ),
                "tag": message.tag,
                "detail_url": reverse_lazy(
                    "mail:message_detail", kwargs={"pk": message.id}
                ),
                "transmissions": list(transmissions),
            }
        )


class TestEmailView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        free_domain = settings.RELAY_FREE_SENDER_DOMAIN
        domain_pk = request.POST["domain"]
        if domain_pk == "free":
            mail_from = f"{request.user.username}@{free_domain}"
            domain = None
        else:
            domain = Domain.objects.get(
                pk=domain_pk,
                organization__in=user_organizations(request.user),
            )
            mail_from = f"postmaster@{domain.name}"

        msg = EmailMessage()
        msg["From"] = mail_from
        msg["To"] = request.user.email
        msg["Subject"] = request.POST.get("subject", "")
        msg.set_content(request.POST.get("body", ""))
        raw_bytes = msg.as_bytes()

        message = Message(
            sender=request.user,
            scope=Message.Scope.OUTGOING,
            rcpt_to=request.user.email,
            mail_from=mail_from,
            subject=request.POST.get("subject", ""),
            message_id=msg.get("Message-ID", ""),
            domain=domain,
            status=Message.Status.PENDING,
            size=len(raw_bytes),
        )
        message.raw_body.save(f"{message.id}.eml", ContentFile(raw_bytes), save=False)
        message.save()

        transaction.on_commit(
            lambda: deliver_message.enqueue(
                message_id=str(message.id),
                rcpt_to=request.user.email,
                mail_from=mail_from,
                domain_id=domain.pk if domain else None,
            )
        )
        return redirect("mail:message_log")
