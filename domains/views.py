"""Domain management views."""

import smtplib
from email.message import EmailMessage

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView, View

from mail.models import Message
from nameserver.services import verify_domain_dns

from .models import Credential, Domain


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        user = self.request.user
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(owner=user),
            "total_domains": Domain.objects.filter(owner=user).count(),
            "total_messages": Message.objects.filter(sender=user).count(),
        }


class DomainListView(LoginRequiredMixin, ListView):
    template_name = "domains/domain_list.html"
    context_object_name = "domains"

    def get_queryset(self):
        return Domain.objects.filter(owner=self.request.user)


class DomainCreateView(LoginRequiredMixin, CreateView):
    model = Domain
    template_name = "domains/domain_form.html"
    fields = ["name"]
    success_url = reverse_lazy("domains:domain_list")

    def form_valid(self, form):
        form.instance.owner = self.request.user
        return super().form_valid(form)


class DomainDetailView(LoginRequiredMixin, DetailView):
    template_name = "domains/domain_detail.html"
    context_object_name = "domain"

    def get_queryset(self):
        return Domain.objects.filter(owner=self.request.user)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "spf_include": f"spf.{platform}",
        }


class DomainVerifyView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        domain = Domain.objects.filter(owner=request.user, pk=pk).first()
        if domain:
            verify_domain_dns(domain)
        return redirect("domains:domain_detail", pk=pk)


class TestEmailView(LoginRequiredMixin, TemplateView):
    template_name = "test_email.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(owner=self.request.user),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
        }

    def post(self, request, *args, **kwargs):
        free_domain = settings.RELAY_FREE_SENDER_DOMAIN
        domain_pk = request.POST["domain"]
        if domain_pk == "free":
            mail_from = f"{request.user.username}@{free_domain}"
        else:
            domain = Domain.objects.get(pk=domain_pk, owner=request.user)
            mail_from = f"postmaster@{domain.name}"
        msg = EmailMessage()
        msg["From"] = mail_from
        msg["To"] = request.user.email
        msg["Subject"] = request.POST.get("subject", "")
        msg.set_content(request.POST.get("body", ""))
        credential = Credential.objects.filter(
            owner=request.user,
            type=Credential.Type.SMTP,
            hold=False,
        ).first() or Credential.objects.create(
            owner=request.user,
            type=Credential.Type.SMTP,
            name="default",
        )
        with smtplib.SMTP(
            settings.RELAY_SMTP_HOST, settings.RELAY_SMTP_LISTEN_PORT
        ) as smtp:
            smtp.ehlo()
            smtp.login(request.user.username, credential.key)
            smtp.send_message(msg)
        return redirect("mail:message_log")
