"""Domain management views."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import CreateView, DeleteView, DetailView, ListView, View

from accounts.views import OrganizationScopedView

from .models import Domain
from .services import verify_domain_dns


class DomainListView(OrganizationScopedView, ListView):
    template_name = "domains/domain_list.html"
    context_object_name = "domains"
    title = _("Domains")
    parent = "tx_email:dashboard"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org)


class DomainCreateView(OrganizationScopedView, CreateView):
    model = Domain
    template_name = "domains/domain_form.html"
    fields = ["name"]
    title = _("New domain")
    parent = "domains:domain-list"

    def form_valid(self, form):
        form.instance.org = self.org
        messages.success(
            self.request,
            _("Domain “%(name)s” added.") % {"name": form.instance.name},
        )
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy("domains:domain-list", kwargs={"org_slug": self.org.slug})


class DomainDetailView(OrganizationScopedView, DetailView):
    template_name = "domains/domain_detail.html"
    context_object_name = "domain"
    parent = "domains:domain-list"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "dkim_cnames": self.object.dkim_cnames,
        }


class DomainVerifyView(OrganizationScopedView, View):
    def post(self, request, org_slug, pk, *args, **kwargs):
        domain = get_object_or_404(Domain, org=self.org, pk=pk)
        verify_domain_dns(domain)
        if all_ok := all(  # noqa: F841
            getattr(domain, f"{field}_status") == Domain.Status.OK
            for field in ("nameserver", "spf", "dkim", "dmarc")
        ):
            messages.success(
                request,
                _("DNS records verified for “%(name)s”.") % {"name": domain.name},
            )
        else:
            messages.error(
                request,
                _("DNS verification failed for “%(name)s”.") % {"name": domain.name},
            )
        return redirect(domain.get_absolute_url())


class DomainDeleteView(OrganizationScopedView, DeleteView):
    model = Domain
    title = _("Delete")
    parent = "domains:domain-list"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org)

    def get_success_url(self):
        return reverse_lazy("domains:domain-list", kwargs={"org_slug": self.org.slug})

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Domain “%(name)s” deleted.") % {"name": self.object.name},
        )
        return super().form_valid(form)
