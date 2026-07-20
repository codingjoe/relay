"""Account views — auth, organization and member management."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.forms import CharField, ChoiceField, Form, ModelForm, SlugField, TextInput
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)
from django.utils.translation import gettext_lazy as _

from .models import Membership, Organization


class OrganizationScopedView(LoginRequiredMixin):
    """Base for org-scoped views: load the org from the URL and enforce membership.

    Subclasses receive `self.org` and `org` is added to the template context.
    The current org is also stashed on the request for the navbar context
    processor. `self.org` is set in `setup()` so subclasses that override
    `dispatch()` (e.g. for admin-only checks) see it before dispatch runs.
    """

    org = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        if request.user.is_authenticated:
            self.org = get_object_or_404(
                request.user.organizations.all(), slug=kwargs["org_slug"]
            )
            request.current_org = self.org

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "org": self.org,
            "breadcrumb_trail": self.breadcrumb_trail(),
        }

    def breadcrumb_trail(self):
        """Return the breadcrumb trail for the current org-scoped view.

        The base trail is ``Relay → Org`` (with both clickable).

        Sub-pages extend it via ``extend_breadcrumb()`` to produce
        ``Relay → Org → Section`` (Section is the current page).
        """
        from django.urls import reverse

        return [
            {"label": "Relay", "url": reverse("home")},
            {
                "label": self.org.slug,
                "url": reverse(
                    "tx_email:dashboard", kwargs={"org_slug": self.org.slug}
                ),
            },
        ]

    def extend_breadcrumb(self, *crumbs):
        """Append crumbs to the base trail.

        Each crumb is ``{"label", "url"}``. ``url`` may be a URL name
        string (reversed with ``self.kwargs``) or a literal path. The
        final crumb is treated as the current page and rendered without
        a link.
        """
        from django.urls import reverse, NoReverseMatch

        middle = []
        for crumb in crumbs[:-1] if len(crumbs) > 1 else []:
            label = crumb["label"]
            url = crumb.get("url")
            if isinstance(url, str) and " " not in url and not url.startswith("/"):
                try:
                    url = reverse(url, kwargs=self.kwargs)
                except NoReverseMatch:
                    pass
            middle.append({"label": label, "url": url})
        trail = self.breadcrumb_trail() + middle
        if crumbs:
            trail.append({"label": crumbs[-1]["label"], "url": None})
        return trail


class LoginView(TemplateView):
    template_name = "login.html"


class OrganizationListView(LoginRequiredMixin, ListView):
    template_name = "accounts/organization_list.html"
    context_object_name = "organizations"

    def get_queryset(self):
        return self.request.user.organizations.all().prefetch_related(
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
        return redirect("tx_email:dashboard", org_slug=org.slug)


class OrganizationForm(ModelForm):
    slug = SlugField(
        widget=TextInput(
            attrs={"pattern": r"[a-z0-9]+(?:-[a-z0-9]+)*"},
        ),
        help_text=_("URL-safe identifier, lowercase letters, digits, and hyphens."),
    )

    class Meta:
        model = Organization
        fields = ["slug"]


class OrganizationDetailView(OrganizationScopedView, DetailView):
    template_name = "accounts/organization_detail.html"
    context_object_name = "organization"

    def get_object(self, queryset=None):
        return self.org

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "memberships": self.org.memberships.select_related("user"),
            "is_admin": self.org.memberships.filter(
                user=self.request.user, role=Membership.Role.ADMIN
            ).exists(),
            "member_form": MembershipForm(),
            "breadcrumb_trail": self.extend_breadcrumb(
                {"label": "Settings"},
            ),
        }


class OrganizationUpdateView(OrganizationScopedView, UpdateView):
    model = Organization
    template_name = "accounts/organization_form.html"
    form_class = OrganizationForm

    def get_object(self, queryset=None):
        return self.org

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return self.org.get_absolute_url()


class OrganizationDeleteView(OrganizationScopedView, DeleteView):
    model = Organization
    template_name = "accounts/organization_confirm_delete.html"
    success_url = reverse_lazy("accounts:organization_list")

    def get_object(self, queryset=None):
        return self.org

    def dispatch(self, request, *args, **kwargs):
        if not self.org.memberships.filter(
            user=request.user, role=Membership.Role.ADMIN
        ).exists():
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class MembershipForm(Form):
    username = CharField(max_length=150)
    role = ChoiceField(choices=Membership.Role, initial=Membership.Role.WRITE)


class MembershipCreateView(OrganizationScopedView, DetailView):
    template_name = "accounts/organization_detail.html"
    context_object_name = "organization"

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
        Membership.objects.get_or_create(
            org=self.org,
            user=user,
            defaults={"role": form.cleaned_data["role"]},
        )
        return redirect(self.org.get_absolute_url())


class MembershipDeleteView(OrganizationScopedView, DeleteView):
    model = Membership
    template_name = "accounts/membership_confirm_delete.html"

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
