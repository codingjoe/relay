"""Account views — auth, organization and member management."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.forms import ChoiceField, CharField, Form
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from .models import Membership, Organization, user_organizations


class LoginView(TemplateView):
    template_name = "login.html"


class OrganizationListView(LoginRequiredMixin, ListView):
    template_name = "accounts/organization_list.html"
    context_object_name = "organizations"

    def get_queryset(self):
        from django.db.models import Prefetch

        return user_organizations(self.request.user).prefetch_related(
            Prefetch(
                "memberships",
                queryset=Membership.objects.filter(user=self.request.user),
                to_attr="my_membership",
            )
        )


class OrganizationDetailView(LoginRequiredMixin, DetailView):
    template_name = "accounts/organization_detail.html"
    context_object_name = "organization"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return user_organizations(self.request.user)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "memberships": self.object.memberships.select_related("user"),
            "is_admin": self.object.memberships.filter(
                user=self.request.user, role=Membership.Role.ADMIN
            ).exists(),
        }


class OrganizationCreateView(LoginRequiredMixin, CreateView):
    model = Organization
    template_name = "accounts/organization_form.html"
    fields = ["name", "slug"]
    success_url = reverse_lazy("accounts:organization_list")

    def form_valid(self, form):
        org = form.save(commit=False)
        org.is_personal = False
        org.save()
        Membership.objects.create(
            organization=org,
            user=self.request.user,
            role=Membership.Role.ADMIN,
        )
        return redirect("accounts:organization_detail", slug=org.slug)


class OrganizationUpdateView(LoginRequiredMixin, UpdateView):
    model = Organization
    template_name = "accounts/organization_form.html"
    fields = ["name"]
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        return user_organizations(self.request.user)

    def dispatch(self, request, *args, **kwargs):
        org = self.get_object()
        if not org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse_lazy("accounts:organization_detail", slug=self.object.slug)


class OrganizationDeleteView(LoginRequiredMixin, DeleteView):
    model = Organization
    template_name = "accounts/organization_confirm_delete.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"
    success_url = reverse_lazy("accounts:organization_list")

    def get_queryset(self):
        return user_organizations(self.request.user).filter(is_personal=False)

    def dispatch(self, request, *args, **kwargs):
        org = self.get_object()
        if not org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class MembershipForm(Form):
    username = CharField(max_length=150)
    role = ChoiceField(choices=Membership.Role.choices, initial=Membership.Role.WRITE)


class MembershipCreateView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/membership_form.html"

    def get_org(self):
        return get_object_or_404(
            user_organizations(self.request.user),
            slug=self.kwargs["slug"],
        )

    def dispatch(self, request, *args, **kwargs):
        org = self.get_org()
        if not org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "organization": self.get_org(),
            "form": MembershipForm(),
        }

    def post(self, request, slug, *args, **kwargs):
        org = self.get_org()
        form = MembershipForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(**kwargs) | {"form": form}
            )
        try:
            user = User.objects.get(username=form.cleaned_data["username"])
        except User.DoesNotExist:
            form.add_error("username", "User not found")
            return self.render_to_response(
                self.get_context_data(**kwargs) | {"form": form, "organization": org}
            )
        _, created = Membership.objects.get_or_create(
            organization=org,
            user=user,
            defaults={"role": form.cleaned_data["role"]},
        )
        return redirect("accounts:organization_detail", slug=org.slug)


class MembershipDeleteView(LoginRequiredMixin, DeleteView):
    model = Membership
    template_name = "accounts/membership_confirm_delete.html"

    def get_object(self, queryset=None):
        org = get_object_or_404(
            user_organizations(self.request.user),
            slug=self.kwargs["slug"],
        )
        if not org.memberships.filter(
            user=self.request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        membership = get_object_or_404(
            Membership, pk=self.kwargs["pk"], organization=org
        )
        if org.is_personal and membership.user == self.request.user:
            raise PermissionDenied(
                "Cannot remove yourself from your personal organization"
            )
        return membership

    def get_success_url(self):
        return reverse_lazy("accounts:organization_detail", slug=self.kwargs["slug"])
