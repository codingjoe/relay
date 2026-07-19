"""Domain management views."""

from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, View

from accounts.views import OrganizationScopedView

from .models import Domain
from .services import verify_domain_dns


class DomainListView(OrganizationScopedView, ListView):
    template_name = "domains/domain_list.html"
    context_object_name = "domains"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org)


class DomainCreateView(OrganizationScopedView, CreateView):
    model = Domain
    template_name = "domains/domain_form.html"
    fields = ["name"]

    def form_valid(self, form):
        form.instance.org = self.org
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("domains:domain_list", kwargs={"org_pk": self.org.pk})


class DomainDetailView(OrganizationScopedView, DetailView):
    template_name = "domains/domain_detail.html"
    context_object_name = "domain"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "spf_include": f"spf.{platform}",
        }


class DomainVerifyView(OrganizationScopedView, View):
    def post(self, request, org_pk, pk, *args, **kwargs):
        domain = get_object_or_404(Domain, org=self.org, pk=pk)
        verify_domain_dns(domain)
        return redirect("domains:domain_detail", org_pk=org_pk, pk=pk)
