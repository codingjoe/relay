from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.forms import (
    CharField,
    ModelForm,
    SlugField,
    TextInput,
)
from django.shortcuts import get_object_or_404, redirect
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import BreadcrumbViewMixin

from .models import Membership, Organization


class OrganizationScopedView(LoginRequiredMixin, BreadcrumbViewMixin):
    """Base for org-scoped views. Loads the org from the URL and enforces membership.

    Subclasses receive `self.org`, and `org` is added to the template context.
    The current org is also stashed on the request for the navbar context
    processor. `self.org` is set in `setup()`, so subclasses that override
    `dispatch()` (for example, for admin-only checks) see it before dispatch runs.
    """

    org = None

    @classmethod
    def get_url(cls, request) -> str | None:
        """Reverse the parent URL using org-scoped kwargs from the request."""
        if not cls.parent:
            return None
        match = request.resolver_match
        kwargs = match.kwargs if match else {}
        try:
            return reverse(cls.parent, kwargs=kwargs)
        except NoReverseMatch:
            return reverse(cls.parent, kwargs={"org_slug": kwargs["org_slug"]})

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        if request.user.is_authenticated:
            self.org = get_object_or_404(
                request.user.organizations.all(), slug=kwargs["org_slug"]
            )
            request.current_org = self.org

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {"org": self.org}


class LoginView(generic.TemplateView):
    template_name = "login.html"


class OrganizationListView(LoginRequiredMixin, generic.ListView):
    context_object_name = "organizations"

    def get_queryset(self):
        return self.request.user.organizations.all().prefetch_related(
            Prefetch(
                "memberships",
                queryset=Membership.objects.filter(user=self.request.user),
                to_attr="my_membership",
            ),
            "memberships__user",
        )

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {"form": OrganizationForm()}

    def get(self, request, *args, **kwargs):
        organizations = self.get_queryset()
        if len(organizations) == 1:
            return redirect("accounts:org-home", org_slug=organizations[0].slug)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        form = OrganizationForm(request.POST)
        if not form.is_valid():
            self.object_list = self.get_queryset()
            return self.render_to_response(
                self.get_context_data(**kwargs) | {"form": form}
            )
        org = form.save(commit=False)
        org.save()
        Membership.objects.create(
            org=org,
            user=request.user,
            role=Membership.Role.ADMIN,
        )
        messages.success(request, _("Created organization “%(org)s”.") % {"org": org})
        return redirect("accounts:org-home", org_slug=org.slug)


class OrganizationForm(ModelForm):
    slug = SlugField(
        max_length=63,
        widget=TextInput(
            attrs={"pattern": r"[a-z0-9]+(?:-[a-z0-9]+)*"},
        ),
        help_text=_(
            "DNS-safe identifier, at most 63 lowercase letters, digits, and hyphens."
        ),
    )

    class Meta:
        model = Organization
        fields = ["slug"]


class OrganizationHomeView(OrganizationScopedView, generic.DetailView):
    template_name_suffix = "_home"
    context_object_name = "organization"
    parent = ""

    @classmethod
    def get_title(cls, request=None) -> str:
        """Return the organization name from the request's current org."""
        if request and hasattr(request, "current_org"):
            return str(request.current_org)
        return ""

    def get_object(self, queryset=None):
        return self.org


class OrganizationDetailView(OrganizationScopedView, generic.DetailView):
    context_object_name = "organization"
    title = _("Settings")
    parent = "accounts:org-home"

    def get_object(self, queryset=None):
        return self.org

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "memberships": self.org.memberships.select_related("user"),
            "is_admin": self.org.memberships.filter(
                user=self.request.user, role=Membership.Role.ADMIN
            ).exists(),
            "member_form": MembershipForm(),
        }


class OrganizationUpdateView(OrganizationScopedView, generic.UpdateView):
    model = Organization
    form_class = OrganizationForm
    title = _("Edit")
    parent = "accounts:org-detail"

    def get_object(self, queryset=None):
        return self.org

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Updated organization “%(org)s”.") % {"org": self.org},
        )
        return super().form_valid(form)

    def get_success_url(self):
        return self.org.get_absolute_url()


class OrganizationDeleteView(OrganizationScopedView, generic.DeleteView):
    model = Organization
    success_url = reverse_lazy("accounts:org-list")
    title = _("Delete")
    parent = "accounts:org-detail"

    def get_object(self, queryset=None):
        return self.org

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Deleted organization “%(org)s”.") % {"org": self.org},
        )
        return super().form_valid(form)


class MembershipForm(ModelForm):
    username = CharField(max_length=150, required=False)

    class Meta:
        model = Membership
        fields = ["role"]


class MembershipCreateView(OrganizationScopedView, generic.DetailView):
    context_object_name = "organization"
    title = _("Settings")
    parent = "accounts:org-home"

    def get_object(self, queryset=None):
        return self.org

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, org_slug, *args, **kwargs):
        self.object = self.org
        form = MembershipForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(
                self.get_context_data() | {"member_form": form}
            )
        try:
            user = User.objects.get(username=form.cleaned_data["username"])
        except User.DoesNotExist:
            form.add_error("username", "User not found")
            return self.render_to_response(
                self.get_context_data() | {"member_form": form}
            )
        _membership, created = Membership.objects.get_or_create(
            org=self.org,
            user=user,
            defaults={"role": form.cleaned_data["role"]},
        )
        if created:
            messages.success(
                request,
                _("Added %(user)s to “%(org)s”.")
                % {"user": user.username, "org": self.org},
            )
        else:
            messages.info(
                request, _("%(user)s is already a member.") % {"user": user.username}
            )
        return redirect(self.org.get_absolute_url())


class MembershipDeleteView(OrganizationScopedView, generic.DeleteView):
    model = Membership
    parent = "accounts:org-detail"

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(Membership, pk=self.kwargs["member_pk"], org=self.org)

    def get_success_url(self):
        return self.org.get_absolute_url()

    def form_valid(self, form):
        username = self.get_object().user.username
        messages.success(
            self.request,
            _("Removed %(user)s from “%(org)s”.") % {"user": username, "org": self.org},
        )
        return super().form_valid(form)


class MembershipUpdateView(OrganizationScopedView, generic.UpdateView):
    model = Membership
    form_class = MembershipForm
    parent = "accounts:org-detail"

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return get_object_or_404(Membership, pk=self.kwargs["member_pk"], org=self.org)

    def get_success_url(self):
        return self.org.get_absolute_url()

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Updated the role of %(user)s to %(role)s.")
            % {"user": self.object.user.username, "role": form.cleaned_data["role"]},
        )
        return super().form_valid(form)
