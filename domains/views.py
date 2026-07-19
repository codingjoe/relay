"""Domain management views."""

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, TemplateView, View

from accounts.models import user_organizations
from mail.models import Message

from .models import Domain
from .services import verify_domain_dns


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard.html"

    def get_context_data(self, **kwargs):
        orgs = user_organizations(self.request.user)
        return super().get_context_data(**kwargs) | {
            "domains": Domain.objects.filter(organization__in=orgs),
            "total_domains": Domain.objects.filter(organization__in=orgs).count(),
            "total_messages": Message.objects.filter(sender=self.request.user).count(),
            "free_sender_domain": settings.RELAY_FREE_SENDER_DOMAIN,
        }


class DomainListView(LoginRequiredMixin, ListView):
    template_name = "domains/domain_list.html"
    context_object_name = "domains"

    def get_queryset(self):
        return Domain.objects.filter(
            organization__in=user_organizations(self.request.user)
        )


class DomainCreateView(LoginRequiredMixin, CreateView):
    model = Domain
    template_name = "domains/domain_form.html"
    fields = ["name"]
    success_url = reverse_lazy("domains:domain_list")

    def form_valid(self, form):
        form.instance.organization = user_organizations(self.request.user).first()
        return super().form_valid(form)


class DomainDetailView(LoginRequiredMixin, DetailView):
    template_name = "domains/domain_detail.html"
    context_object_name = "domain"

    def get_queryset(self):
        return Domain.objects.filter(
            organization__in=user_organizations(self.request.user)
        )

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "spf_include": f"spf.{platform}",
        }


class DomainVerifyView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        domain = Domain.objects.filter(
            organization__in=user_organizations(request.user), pk=pk
        ).first()
        if domain:
            verify_domain_dns(domain)
        return redirect("domains:domain_detail", pk=pk)
