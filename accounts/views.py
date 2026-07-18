"""Account views — auth, SMTP credentials."""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    ListView,
    TemplateView,
)

from domains.models import Credential


class LoginView(TemplateView):
    template_name = "login.html"


class CredentialListView(LoginRequiredMixin, ListView):
    template_name = "accounts/credential_list.html"
    context_object_name = "credentials"

    def get_queryset(self):
        return Credential.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "smtp_hostname": f"smtp.{platform}",
            "smtp_port": settings.RELAY_SMTP_SUBMISSION_PORT,
        }


class CredentialCreateView(LoginRequiredMixin, CreateView):
    model = Credential
    template_name = "accounts/credential_form.html"
    fields = ["name"]
    success_url = reverse_lazy("accounts:credential_list")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class CredentialDeleteView(LoginRequiredMixin, DeleteView):
    model = Credential
    success_url = reverse_lazy("accounts:credential_list")

    def get_queryset(self):
        return Credential.objects.filter(owner=self.request.user)
