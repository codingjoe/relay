"""Account views — auth, organization and member management."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.forms import CharField, ModelForm, SlugField, TextInput
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views.generic import (
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

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

        The base trail is ``Org`` (clickable). For email namespaces
        (tx_email, smtp, domains) an ``Email`` crumb is appended, linking
        to the email dashboard.

        Sub-pages extend it via ``extend_breadcrumb()`` to produce
        ``Org → Email → Section`` (Section is the current page).
        """
        from django.urls import reverse

        trail = [
            {
                "label": self.org.slug,
                "url": reverse(
                    "accounts:organization_home", kwargs={"org_slug": self.org.slug}
                ),
            },
        ]
        if self.request.resolver_match.namespace in ("tx_email", "smtp", "domains"):
            trail.append(
                {
                    "label": _("Email"),
                    "url": reverse(
                        "tx_email:dashboard", kwargs={"org_slug": self.org.slug}
                    ),
                }
            )
        return trail

    def extend_breadcrumb(self, *crumbs):
        """Append crumbs to the base trail.

        Each crumb is ``{"label", "url"}``. ``url`` may be a URL name
        string (reversed with ``self.kwargs``) or a literal path. The
        final crumb is treated as the current page and rendered without
        a link. With no arguments, the last base crumb becomes the
        current page (used by the email dashboard).
        """
        from django.urls import reverse, NoReverseMatch

        trail = self.breadcrumb_trail()
        if not crumbs:
            if trail:
                trail = trail[:-1] + [{"label": trail[-1]["label"], "url": None}]
            return trail
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
        trail = trail + middle
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
            ),
            "memberships__user",
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
        messages.success(
            request, _("Organization “%(slug)s” created.") % {"slug": org.slug}
        )
        return redirect("accounts:organization_home", org_slug=org.slug)


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


class OrganizationHomeView(OrganizationScopedView, DetailView):
    template_name = "accounts/organization_home.html"
    context_object_name = "organization"

    def get_object(self, queryset=None):
        return self.org

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "breadcrumb_trail": [{"label": self.org.slug, "url": None}],
        }


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

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Organization “%(slug)s” updated.") % {"slug": self.org.slug},
        )
        return super().form_valid(form)

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

    def form_valid(self, form):
        messages.success(
            self.request,
            _("Organization “%(slug)s” deleted.") % {"slug": self.org.slug},
        )
        return super().form_valid(form)


class MembershipForm(ModelForm):
    username = CharField(max_length=150, required=False)

    class Meta:
        model = Membership
        fields = ["role"]


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
        membership, created = Membership.objects.get_or_create(
            org=self.org,
            user=user,
            defaults={"role": form.cleaned_data["role"]},
        )
        if created:
            messages.success(
                request,
                _("%(user)s added to “%(org)s”.")
                % {"user": user.username, "org": self.org.slug},
            )
        else:
            messages.info(
                request, _("%(user)s is already a member.") % {"user": user.username}
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

    def form_valid(self, form):
        username = self.get_object().user.username
        messages.success(
            self.request,
            _("%(user)s removed from “%(org)s”.")
            % {"user": username, "org": self.org.slug},
        )
        return super().form_valid(form)


class MembershipUpdateView(OrganizationScopedView, UpdateView):
    model = Membership
    form_class = MembershipForm
    template_name = "accounts/membership_form.html"

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
            _("%(user)s role updated to %(role)s.")
            % {"user": self.object.user.username, "role": form.cleaned_data["role"]},
        )
        return super().form_valid(form)
