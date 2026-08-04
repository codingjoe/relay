"""SMTP views — outgoing message detail, test email, and credential management."""

from email.message import EmailMessage

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import BadRequest, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, DetailView, ListView, View

from accounts.views import OrganizationScopedView
from domains.models import Domain

from .charts import build_suppression_chart
from .models import OutgoingMessage, SmtpCredential, SuppressionEntry, Transmission
from .tasks import deliver_message


class OutgoingMessageDetailView(OrganizationScopedView, DetailView):
    template_name = "smtp/message_detail.html"
    context_object_name = "message"
    parent = "message:message-list"

    def get_queryset(self):
        return OutgoingMessage.objects.filter(org=self.org).select_related(
            "domain", "credential"
        )

    def get_object(self, queryset=None):
        return get_object_or_404(queryset or self.get_queryset(), pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        message = self.object
        parsed = message.parsed_email()
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
        return context | {
            "headers": headers,
            "dkim_signatures": dkim_signatures,
            "received": [v for k, v in headers if k.lower() == "received"],
            "body": parsed.get_payload(decode=True) or "",
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

        if SuppressionEntry.objects.is_suppressed(self.org, request.user.email):
            messages.error(request, _("Recipient is on the suppression list."))
            return redirect("message:message-list", org_slug=org_slug)

        msg = EmailMessage()
        msg["From"] = mail_from
        msg["To"] = request.user.email
        msg["Subject"] = request.POST.get("subject", "")
        msg.set_content(request.POST.get("body", ""))
        raw_bytes = msg.as_bytes()

        message = OutgoingMessage.objects.create(
            sender=request.user,
            org=self.org,
            rcpt_to=request.user.email,
            mail_from=mail_from,
            subject=request.POST.get("subject", ""),
            message_id=msg.get("Message-ID", ""),
            domain=domain,
            raw_body=SimpleUploadedFile(
                f"{msg.get('Message-ID', 'message')}.eml", raw_bytes
            ),
        )

        transaction.on_commit(
            lambda: deliver_message.enqueue(
                message_id=str(message.id),
                rcpt_to=request.user.email,
                mail_from=mail_from,
                domain_id=domain.pk if domain else None,
            )
        )
        messages.success(request, _("Queued test message for delivery."))
        return redirect("message:message-list", org_slug=org_slug)


class SmtpCredentialListView(OrganizationScopedView, ListView):
    template_name = "smtp/credential_list.html"
    context_object_name = "credentials"
    title = _("SMTP credentials")
    parent = "email-dashboard:dashboard"

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


class SuppressionListView(OrganizationScopedView, ListView):
    model = SuppressionEntry
    title = _("Suppression list")
    parent = "accounts:org-home"

    def get_queryset(self):
        return self.model.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "suppression_chart": build_suppression_chart(self.org),
        }


class SuppressionViewMixin:
    def get_email(self, request):
        email = request.POST.get("email", "").strip()
        try:
            validate_email(email)
        except ValidationError:
            raise BadRequest(_("Enter a valid email address."))
        return email


class SuppressionCreateView(SuppressionViewMixin, OrganizationScopedView, View):
    def post(self, request, org_slug, *args, **kwargs):
        email = self.get_email(request)
        if SuppressionEntry.objects.create_or_update(
            self.org, email, reason=SuppressionEntry.Reason.MANUAL
        )[1]:
            messages.success(request, _("Added address to suppression list."))
        else:
            messages.info(request, _("Address is already on the suppression list."))
        return redirect("smtp:suppression-list", org_slug=org_slug)


class SuppressionRemoveView(SuppressionViewMixin, OrganizationScopedView, View):
    def post(self, request, org_slug, *args, **kwargs):
        email = self.get_email(request)
        if SuppressionEntry.objects.filter(
            org=self.org, address_hash__email=email
        ).delete()[0]:
            messages.success(request, _("Removed address from suppression list."))
        else:
            messages.info(request, _("Address was not on the suppression list."))
        return redirect("smtp:suppression-list", org_slug=org_slug)


class SuppressionCheckView(SuppressionViewMixin, OrganizationScopedView, View):
    def post(self, request, org_slug, *args, **kwargs):
        email = self.get_email(request)
        if SuppressionEntry.objects.is_suppressed(self.org, email):
            messages.warning(request, _("Address is on the suppression list."))
        else:
            messages.success(request, _("Address is not on the suppression list."))
        return redirect("smtp:suppression-list", org_slug=org_slug)
