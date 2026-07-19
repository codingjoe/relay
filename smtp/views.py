"""SMTP credential management views."""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import DeleteView, ListView, View

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
        context = super().get_context_data(**kwargs) | {
            "smtp_hostname": f"smtp.{platform}",
            "smtp_port": settings.RELAY_SMTP_SUBMISSION_PORT,
        }
        if raw_key := self.request.session.pop("raw_key", None):
            context["raw_key"] = raw_key
        return context


class SmtpCredentialCreateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        org = user_organizations(request.user).first()
        if org is None:
            return redirect("smtp:credential_list")
        credential, raw_key = SmtpCredential.create(
            organization=org,
            type=SmtpCredential.Type.SMTP,
            name=request.POST.get("name", ""),
        )
        request.session["raw_key"] = raw_key
        return redirect("smtp:credential_list")


class SmtpCredentialDeleteView(LoginRequiredMixin, DeleteView):
    model = SmtpCredential
    success_url = reverse_lazy("smtp:credential_list")

    def get_queryset(self):
        return SmtpCredential.objects.filter(
            organization__in=user_organizations(self.request.user)
        )
