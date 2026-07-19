"""SMTP credential management views."""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, ListView, TemplateView

from accounts.models import user_organizations

from .models import SmtpCredential


class SmtpCredentialListView(LoginRequiredMixin, ListView):
    template_name = "smtp/credential_list.html"
    context_object_name = "credentials"

    def get_queryset(self):
        return SmtpCredential.objects.filter(
            organization__in=user_organizations(self.request.user)
        )

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "smtp_hostname": f"smtp.{platform}",
            "smtp_port": settings.RELAY_SMTP_SUBMISSION_PORT,
        }


class SmtpCredentialCreateView(LoginRequiredMixin, TemplateView):
    template_name = "smtp/credential_form.html"

    def post(self, request, *args, **kwargs):
        org = user_organizations(request.user).first()
        if org is None:
            return redirect("smtp:credential_list")
        credential, raw_key = SmtpCredential.create(
            organization=org,
            type=SmtpCredential.Type.SMTP,
            name=request.POST.get("name", ""),
        )
        return self.render_to_response(
            self.get_context_data(**kwargs)
            | {"raw_key": raw_key, "credential": credential}
        )


class SmtpCredentialDeleteView(LoginRequiredMixin, DeleteView):
    model = SmtpCredential
    success_url = reverse_lazy("smtp:credential_list")

    def get_queryset(self):
        return SmtpCredential.objects.filter(
            organization__in=user_organizations(self.request.user)
        )
