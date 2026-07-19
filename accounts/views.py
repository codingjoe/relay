"""Account views — auth, organization and member management."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.forms import CharField, ChoiceField, Form
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
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

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {"form": OrganizationForm()}

    def post(self, request, *args, **kwargs):
        form = OrganizationForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(**kwargs) | {"form": form}
            )
        org = form.save(commit=False)
        org.save()
        Membership.objects.create(
            organization=org,
            user=request.user,
            role=Membership.Role.ADMIN,
        )
        return redirect("accounts:organization_detail", pk=org.pk)


class OrganizationForm(Form):
    name = CharField(max_length=255)


class OrganizationDetailView(LoginRequiredMixin, DetailView):
    template_name = "accounts/organization_detail.html"
    context_object_name = "organization"

    def get_queryset(self):
        return user_organizations(self.request.user)

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "memberships": self.object.memberships.select_related("user"),
            "is_admin": self.object.memberships.filter(
                user=self.request.user, role=Membership.Role.ADMIN
            ).exists(),
            "member_form": MembershipForm(),
        }


class OrganizationUpdateView(LoginRequiredMixin, UpdateView):
    model = Organization
    template_name = "accounts/organization_form.html"
    fields = ["name"]

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
        return reverse_lazy(
            "accounts:organization_detail", kwargs={"pk": self.object.pk}
        )


class OrganizationDeleteView(LoginRequiredMixin, DeleteView):
    model = Organization
    template_name = "accounts/organization_confirm_delete.html"
    success_url = reverse_lazy("accounts:organization_list")

    def get_queryset(self):
        return user_organizations(self.request.user)

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


class MembershipCreateView(LoginRequiredMixin, DetailView):
    template_name = "accounts/organization_detail.html"
    context_object_name = "organization"

    def get_queryset(self):
        return user_organizations(self.request.user)

    def get_object(self):
        return get_object_or_404(
            user_organizations(self.request.user), pk=self.kwargs["pk"]
        )

    def dispatch(self, request, *args, **kwargs):
        org = self.get_object()
        if not org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, pk, *args, **kwargs):
        org = self.get_object()
        form = MembershipForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data(object=org) | {"member_form": form}
            )
        try:
            user = User.objects.get(username=form.cleaned_data["username"])
        except User.DoesNotExist:
            form.add_error("username", "User not found")
            return self.render_to_response(
                self.get_context_data(object=org) | {"member_form": form}
            )
        Membership.objects.get_or_create(
            organization=org,
            user=user,
            defaults={"role": form.cleaned_data["role"]},
        )
        return redirect("accounts:organization_detail", pk=org.pk)


class MembershipDeleteView(LoginRequiredMixin, DeleteView):
    model = Membership
    template_name = "accounts/membership_confirm_delete.html"

    def get_object(self, queryset=None):
        org = get_object_or_404(
            user_organizations(self.request.user), pk=self.kwargs["pk"]
        )
        if not org.memberships.filter(
            user=self.request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return get_object_or_404(
            Membership, pk=self.kwargs["member_pk"], organization=org
        )

    def get_success_url(self):
        return reverse_lazy(
            "accounts:organization_detail", kwargs={"pk": self.kwargs["pk"]}
        )
