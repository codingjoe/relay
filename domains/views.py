"""Domain management views."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from .models import Domain
from .services import verify_domain_dns


class DomainListView(LoginRequiredMixin, ListView):
    template_name = "domains/domain_list.html"
    context_object_name = "domains"

    def get_queryset(self):
        return Domain.objects.filter(org__in=self.request.user.organizations.all())


class DomainCreateView(LoginRequiredMixin, CreateView):
    model = Domain
    template_name = "domains/domain_form.html"
    fields = ["name"]
    success_url = reverse_lazy("domains:domain_list")

    def form_valid(self, form):
        form.instance.org = self.request.user.organizations.first()
        return super().form_valid(form)


class DomainDetailView(LoginRequiredMixin, DetailView):
    template_name = "domains/domain_detail.html"
    context_object_name = "domain"

    def get_queryset(self):
        return Domain.objects.filter(org__in=self.request.user.organizations.all())

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "spf_include": f"spf.{platform}",
        }


class DomainVerifyView(LoginRequiredMixin, View):
    def post(self, request, pk, *args, **kwargs):
        domain = Domain.objects.filter(
            org__in=request.user.organizations.all(), pk=pk
        ).first()
        if domain:
            verify_domain_dns(domain)
        return redirect("domains:domain_detail", pk=pk)
