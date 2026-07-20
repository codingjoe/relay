"""SMTP views — outgoing message log, test email, and credential management."""

from email import message_from_bytes
from email.message import EmailMessage

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView, View

from accounts.views import OrganizationScopedView
from domains.models import Domain

from .models import OutgoingMessage, SmtpCredential, Transmission
from .tasks import deliver_message


class OutgoingMessageLogView(OrganizationScopedView, ListView):
    template_name = "smtp/message_log.html"
    context_object_name = "messages"
    paginate_by = 50

    def get_queryset(self):
        qs = OutgoingMessage.objects.filter(org=self.org).select_related("domain")
        if domain := self.request.GET.get("domain"):
            qs = qs.filter(domain_id=domain)
        if status := self.request.GET.get("status"):
            qs = qs.filter(status=status)
        if search := self.request.GET.get("search"):
            qs = qs.filter(rcpt_to__icontains=search)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(org=self.org),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
            "status_choices": OutgoingMessage.Status.choices,
            "filters": {
                "domain": self.request.GET.get("domain", ""),
                "status": self.request.GET.get("status", ""),
                "search": self.request.GET.get("search", ""),
            },
        }


class OutgoingMessageDetailView(OrganizationScopedView, DetailView):
    template_name = "smtp/message_detail.html"
    context_object_name = "message"

    def get_queryset(self):
        return OutgoingMessage.objects.filter(org=self.org).select_related(
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


class OutgoingMessageModalView(OrganizationScopedView, View):
    def get(self, request, org_slug, pk, *args, **kwargs):
        message = get_object_or_404(
            OutgoingMessage.objects.filter(org=self.org).select_related(
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
                "status": message.get_status_display(),
                "received_at": message.received_at.isoformat(),
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
                "detail_url": message.get_absolute_url(),
                "transmissions": list(transmissions),
            }
        )


class TestEmailView(OrganizationScopedView, View):
    def post(self, request, org_slug, *args, **kwargs):
        free_domain = settings.RELAY_FREE_SENDER_DOMAIN
        domain_pk = request.POST["domain"]
        if domain_pk == "free":
            mail_from = f"{request.user.username}@{free_domain}"
            domain = None
        else:
            domain = Domain.objects.get(pk=domain_pk, org=self.org)
            mail_from = f"postmaster@{domain.name}"

        msg = EmailMessage()
        msg["From"] = mail_from
        msg["To"] = request.user.email
        msg["Subject"] = request.POST.get("subject", "")
        msg.set_content(request.POST.get("body", ""))
        raw_bytes = msg.as_bytes()

        message = OutgoingMessage(
            sender=request.user,
            org=self.org,
            rcpt_to=request.user.email,
            mail_from=mail_from,
            subject=request.POST.get("subject", ""),
            message_id=msg.get("Message-ID", ""),
            domain=domain,
            status=OutgoingMessage.Status.PENDING,
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
        return redirect("smtp:message_log", org_slug=org_slug)


class SmtpCredentialListView(OrganizationScopedView, ListView):
    template_name = "smtp/credential_list.html"
    context_object_name = "credentials"

    def get_queryset(self):
        return SmtpCredential.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        context = super().get_context_data(**kwargs) | {
            "smtp_hostname": f"smtp.{platform}",
            "smtp_port": settings.RELAY_SMTP_SUBMISSION_PORT,
        }
        if raw_key := self.request.session.pop("raw_key", None):
            context["raw_key"] = raw_key
        return context


class SmtpCredentialCreateView(OrganizationScopedView, View):
    def post(self, request, org_slug, *args, **kwargs):
        credential, raw_key = SmtpCredential.objects.create_with_key(
            org=self.org,
            type=SmtpCredential.Type.SMTP,
            name=request.POST.get("name", ""),
        )
        request.session["raw_key"] = raw_key
        return redirect("smtp:credential_list", org_slug=org_slug)


class SmtpCredentialDeleteView(OrganizationScopedView, DeleteView):
    model = SmtpCredential

    def get_queryset(self):
        return SmtpCredential.objects.filter(org=self.org)

    def get_success_url(self):
        return reverse_lazy("smtp:credential_list", kwargs={"org_slug": self.org.slug})
