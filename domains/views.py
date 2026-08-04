from django.conf import settings
from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic

from accounts.views import OrganizationScopedView

from .models import Domain
from .services import verify_domain_dns


class DomainListView(OrganizationScopedView, generic.ListView):
    context_object_name = "domains"
    title = _("Domains")
    parent = "email-dashboard:dashboard"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org)


class DomainCreateView(OrganizationScopedView, generic.CreateView):
    model = Domain
    fields = ["name"]
    title = _("New domain")
    parent = "domains:domain-list"

    def form_valid(self, form):
        form.instance.org = self.org
        messages.success(
            self.request,
            _("Added domain “%(name)s”.") % {"name": form.instance.name},
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        for error in form.errors.get("name", []):
            messages.error(self.request, error)
        return redirect("domains:domain-list", org_slug=self.org.slug)

    def get_success_url(self):
        return reverse_lazy("domains:domain-list", kwargs={"org_slug": self.org.slug})


class DomainDetailView(OrganizationScopedView, generic.DetailView):
    context_object_name = "domain"
    parent = "domains:domain-list"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org, is_managed=False)

    def get_context_data(self, **kwargs):
        platform = self.request.get_host().split(":")[0]
        return super().get_context_data(**kwargs) | {
            "nameservers": [f"ns1.{platform}", f"ns2.{platform}"],
            "dkim_cnames": self.object.dkim_cnames,
        }


class DomainVerifyView(OrganizationScopedView, generic.View):
    def post(self, request, org_slug, pk, *args, **kwargs):
        domain = get_object_or_404(
            Domain,
            org=self.org,
            is_managed=False,
            pk=pk,
        )
        verify_domain_dns(domain)
        if all_ok := all(  # noqa: F841
            getattr(domain, f"{field}_status") == Domain.Status.OK
            for field in ("nameserver", "spf", "dkim", "dmarc")
        ):
            messages.success(request, _("DNS verification passed."))
        else:
            messages.error(request, _("DNS verification failed."))
        return redirect(domain.get_absolute_url())


class DomainDeleteView(OrganizationScopedView, generic.DeleteView):
    model = Domain
    title = _("Delete")
    parent = "domains:domain-list"

    def get_queryset(self):
        return Domain.objects.filter(org=self.org, is_managed=False)

    def get_success_url(self):
        return reverse_lazy("domains:domain-list", kwargs={"org_slug": self.org.slug})

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Deleted domain “%(name)s”.") % {"name": self.object.name},
        )
        return super().form_valid(form)


class MtaStsPolicyView(generic.DetailView):
    model = Domain
    content_type = "text/plain"

    def get_template_names(self):
        return ["domains/mta_sts.txt"]

    def get_object(self, queryset=None):
        host = self.request.META.get("HTTP_HOST", "").split(":")[0].lower()
        name = host.removeprefix("mta-sts.")
        try:
            return Domain.objects.root_for(name)
        except Domain.DoesNotExist:
            raise Http404

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "mta_sts_mode": settings.RELAY_MTA_STS_MODE,
            "mta_sts_max_age": settings.RELAY_MTA_STS_MAX_AGE,
        }

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        response["Cache-Control"] = f"public, max-age={settings.RELAY_MTA_STS_MAX_AGE}"
        response["Vary"] = "Host"
        return response
