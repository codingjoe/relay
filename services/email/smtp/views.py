"""SMTP views — outgoing message detail, test email, and credential management."""

from email import message_from_bytes
from email.message import EmailMessage

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, DetailView, ListView, RedirectView, View

from accounts.views import OrganizationScopedView
from domains.models import Domain

from .models import OutgoingMessage, SmtpCredential, Transmission
from .tasks import deliver_message


class OutgoingMessageDetailView(OrganizationScopedView, DetailView):
    template_name = "smtp/message_detail.html"
    context_object_name = "message"
    parent = "message:contact-messages"

    def get_queryset(self):
        return OutgoingMessage.objects.filter(org=self.org).select_related(
            "domain", "credential"
        )

    def get_object(self, queryset=None):
        return get_object_or_404(queryset or self.get_queryset(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        message = self.object
        headers = dkim_signatures = received = []
        body = ""
        if message.raw_body:
            try:
                raw_bytes = message.raw_body.read()
            except FileNotFoundError:
                raw_bytes = b""
            if raw_bytes:
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
                body = raw_bytes.decode("utf-8", errors="replace")
        return context | {
            "headers": headers,
            "dkim_signatures": dkim_signatures,
            "received": received,
            "body": body,
            "transmissions": Transmission.objects.filter(message=message),
        }


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
        messages.success(request, _("Queued test message for delivery."))
        return redirect("smtp:message-list", org_slug=org_slug)


class SmtpCredentialListView(OrganizationScopedView, ListView):
    template_name = "smtp/credential_list.html"
    context_object_name = "credentials"
    title = _("SMTP credentials")
    parent = "dashboard:dashboard"

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
        messages.success(
            request,
            _("Created SMTP credential “%(name)s”.") % {"name": credential.name},
        )
        return redirect("smtp:credential-list", org_slug=org_slug)


class SmtpCredentialDeleteView(OrganizationScopedView, DeleteView):
    model = SmtpCredential
    title = _("Delete")
    parent = "smtp:credential-list"

    def get_queryset(self):
        return SmtpCredential.objects.filter(org=self.org)

    def get_success_url(self):
        return reverse_lazy("smtp:credential-list", kwargs={"org_slug": self.org.slug})

    def form_valid(self, form):
        messages.success(self.request, _("Deleted SMTP credential."))
        return super().form_valid(form)


class MessageListRedirectView(OrganizationScopedView, RedirectView):
    """Redirect the legacy message-list URL to the merged Messages view."""

    permanent = False
    query_string = True
    direction: str = "all"

    def get_redirect_url(self, *args, **kwargs):
        url = reverse("message:contact-messages", kwargs={"org_slug": self.org.slug})
        return f"{url}?direction={self.direction}"
