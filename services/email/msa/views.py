from django.conf import settings
from django.contrib import messages
from django.core.exceptions import BadRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.views import generic
from django_letter.exceptions import InvalidUserError

from abstract.views import NoStoreCacheMixin
from accounts.views import OrganizationScopedView
from domains.models import Domain
from services.email.message.views import MessageDetailView

from .charts import build_suppression_chart
from .emails import TestEmail
from .forms import SuppressionEntryForm
from .handlers import submit_relay_message
from .models import MsaCredential, OutgoingMessage, SuppressionEntry


class OutgoingMessageDetailView(MessageDetailView):
    def get_template_names(self):
        return ["msa/message_detail.html"]

    def get_queryset(self):
        return OutgoingMessage.objects.filter(org=self.org).select_related(
            "domain", "credential", "content_type"
        )


class TestEmailView(OrganizationScopedView, generic.View):
    def post(self, request, org_slug, *args, **kwargs):
        started_at = timezone.now()
        try:
            domain = Domain.objects.get(org=self.org, is_managed=True)
        except Domain.DoesNotExist:
            messages.error(request, _("Add a sending domain first."))
            return redirect("message:message-list", org_slug=org_slug)

        mail_from = f"{settings.RELAY_POSTMASTER_LOCAL_PART}@{domain.name}"
        try:
            email = TestEmail.to_user(
                request.user,
                domain=domain,
                from_email=mail_from,
                language=translation.get_language(),
            )
        except InvalidUserError:
            messages.error(request, _("Your account cannot receive email."))
            return redirect("message:message-list", org_slug=org_slug)

        if SuppressionEntry.objects.is_suppressed(self.org, request.user.email):
            messages.error(request, _("Recipient is on the suppression list."))
            return redirect("message:message-list", org_slug=org_slug)

        submit_relay_message(
            org=self.org,
            domain=domain,
            email=email,
            mail_from=mail_from,
            rcpt_to=request.user.email,
            started_at=started_at,
            ssl=request.is_secure(),
            client_ip=request.META.get("REMOTE_ADDR", ""),
        )
        messages.success(request, _("Queued test message for delivery."))
        return redirect("message:message-list", org_slug=org_slug)


class MsaCredentialListView(OrganizationScopedView, generic.ListView):
    def get_template_names(self):
        return ["msa/credential_list.html"]

    context_object_name = "credentials"
    title = _("SMTP credentials")
    parent = "email-dashboard:dashboard"

    def get_queryset(self):
        return MsaCredential.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        implicit_tls_ports = settings.RELAY_SMTP_IMPLICIT_TLS_PORTS
        starttls_ports = tuple(
            p
            for p in settings.RELAY_SMTP_SUBMISSION_PORTS
            if p not in implicit_tls_ports
        )
        context = super().get_context_data(**kwargs) | {
            "smtp_hostname": f"smtp.{platform}",
            "smtp_starttls_ports": starttls_ports,
            "smtp_implicit_tls_ports": implicit_tls_ports,
        }
        if raw_key := self.request.session.pop("raw_key", None):
            context["raw_key"] = raw_key
        return context


class MsaCredentialCreateView(OrganizationScopedView, generic.View):
    def post(self, request, org_slug, *args, **kwargs):
        credential, raw_key = MsaCredential.objects.create_with_key(
            org=self.org,
            type=MsaCredential.Type.SMTP,
            name=request.POST.get("name", ""),
        )
        request.session["raw_key"] = raw_key
        messages.success(
            request,
            _("Created SMTP credential “%(name)s”.") % {"name": credential.name},
        )
        return redirect("msa:credential-list", org_slug=org_slug)


class MsaCredentialDeleteView(OrganizationScopedView, generic.DeleteView):
    model = MsaCredential
    title = _("Delete")
    parent = "msa:credential-list"

    def get_queryset(self):
        return MsaCredential.objects.filter(org=self.org)

    def get_success_url(self):
        return reverse_lazy("msa:credential-list", kwargs={"org_slug": self.org.slug})

    def form_valid(self, form):
        messages.success(self.request, _("Deleted SMTP credential."))
        return super().form_valid(form)


class SuppressionListView(OrganizationScopedView, NoStoreCacheMixin, generic.ListView):
    model = SuppressionEntry
    title = _("Suppression list")
    parent = "accounts:org-home"

    def get_queryset(self):
        return self.model.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "suppression_chart": build_suppression_chart(self.org),
        }


class SuppressionCreateView(OrganizationScopedView, generic.FormView):
    http_method_names = ["post"]
    form_class = SuppressionEntryForm
    parent = "msa:suppression-list"

    def form_invalid(self, form):
        raise BadRequest

    def form_valid(self, form):
        if SuppressionEntry.objects.create_or_update(
            org=self.org,
            email=form.cleaned_data["email"],
            reason=SuppressionEntry.Reason.MANUAL,
        )[1]:
            messages.success(self.request, _("Added address to suppression list."))
        else:
            messages.info(
                self.request, _("Address is already on the suppression list.")
            )
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("msa:suppression-list", kwargs={"org_slug": self.org.slug})


class SuppressionRemoveView(OrganizationScopedView, generic.DeleteView):
    http_method_names = ["post"]
    model = SuppressionEntry
    parent = "msa:suppression-list"

    def get_queryset(self):
        return self.model.objects.filter(org=self.org)

    def get_object(self, queryset=None):
        qs = (queryset or self.get_queryset()).filter(
            address_hash__email=self.request.POST.get("email", "")
        )
        return get_object_or_404(qs)

    def form_valid(self, form):
        messages.success(self.request, _("Removed address from suppression list."))
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("msa:suppression-list", kwargs={"org_slug": self.org.slug})


class SuppressionCheckView(OrganizationScopedView, generic.FormView):
    http_method_names = ["post"]
    form_class = SuppressionEntryForm
    parent = "msa:suppression-list"

    def form_invalid(self, form):
        raise BadRequest

    def form_valid(self, form):
        if SuppressionEntry.objects.is_suppressed(self.org, form.cleaned_data["email"]):
            messages.warning(self.request, _("Address is on the suppression list."))
        else:
            messages.success(self.request, _("Address is not on the suppression list."))
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse("msa:suppression-list", kwargs={"org_slug": self.org.slug})
