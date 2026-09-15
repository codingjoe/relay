from collections.abc import Mapping

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.forms import (
    CharField,
    EmailField,
    ModelForm,
    SlugField,
    TextInput,
)
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import NoReverseMatch, reverse, reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic

from abstract.views import BreadcrumbViewMixin
from kms.envelope import decode_key
from kms.models import OrgEncryptionKey

from .models import (
    EmailVerification,
    Membership,
    MembershipEncryptionKey,
    Organization,
    UserEncryptionKey,
    organization_slug_validator,
)
from .tasks import send_verification_email


class OrganizationScopedView(LoginRequiredMixin, BreadcrumbViewMixin):
    """
    Base for org-scoped views. Loads the org from the URL and enforces membership.

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

    user_orgs = None

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        if request.user.is_authenticated:
            self.user_orgs = list(request.user.organizations.all())
            self.org = next(
                (org for org in self.user_orgs if org.slug == kwargs["org_slug"]),
                None,
            )
            if self.org is None:
                raise Http404
            request.current_org = self.org

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {
            "org": self.org,
            "current_org": self.org,
            "user_orgs": self.user_orgs,
        }


class SignupForm(UserCreationForm):
    """Create a user whose username doubles as their organization slug."""

    username = SlugField(
        max_length=63,
        validators=[organization_slug_validator],
        help_text=_(
            "At most 63 lowercase letters, digits, and hyphens. Used as your "
            "organization URL."
        ),
    )
    email = EmailField(
        help_text=_(
            "Receives account notifications. Verify it after signup to receive mail."
        ),
    )

    class Meta(UserCreationForm.Meta):
        fields = UserCreationForm.Meta.fields + ("email",)

    def clean_username(self):
        """Reject usernames that collide with an existing organization slug."""
        if Organization.objects.filter(slug=self.cleaned_data["username"]).exists():
            raise ValidationError(_("This username is already taken."))
        return self.cleaned_data["username"]

    def clean_email(self):
        """Reject emails another account already uses, case-insensitively."""
        if User.objects.filter(email__iexact=self.cleaned_data["email"]).exists():
            raise ValidationError(_("This email is already in use."))
        return self.cleaned_data["email"]


KEY_FIELDS = (
    "org_public_key",
    "user_public_key",
    "encrypted_master_key",
    "encrypted_private_key",
    "sealed_org_private_key",
    "recovery_sealed_org_private_key",
)

PUBLIC_KEY_SIZE_BYTES = 32
KEY_ID_MAX_LENGTH = 16


def validate_encryption_keys(keys: Mapping[str, str]) -> None:
    """Validate client-supplied key payloads before they reach the database."""
    for name, value in keys.items():
        if not isinstance(value, str):
            # ValueError, not TypeError: callers map ValueError to HTTP 400.
            raise ValueError(_("Invalid encryption key payload."))  # noqa: TRY004
        match name:
            case "key_id" | "org_key_id" | "user_key_id":
                valid = len(value) <= KEY_ID_MAX_LENGTH
            case "public_key" | "org_public_key" | "user_public_key":
                try:
                    valid = len(decode_key(value)) == PUBLIC_KEY_SIZE_BYTES
                except ValueError:
                    valid = False
            case _:
                valid = bool(value)
        if not valid:
            raise ValueError(_("Invalid encryption key payload."))


def create_encryption_keys(
    org: Organization,
    user: User,
    membership: Membership,
    keys: Mapping[str, str],
) -> tuple[OrgEncryptionKey, UserEncryptionKey]:
    """Create the org, user, and membership encryption keys."""
    org_key = OrgEncryptionKey(
        org=org,
        public_key=keys["org_public_key"],
        key_id=keys.get("org_key_id", ""),
        is_active=True,
        recovery_sealed_org_private_key=keys["recovery_sealed_org_private_key"],
    )
    org_key.save(force_insert=True)
    user_key = UserEncryptionKey(
        user=user,
        public_key=keys["user_public_key"],
        key_id=keys.get("user_key_id", ""),
        encrypted_master_key=keys["encrypted_master_key"],
        encrypted_private_key=keys["encrypted_private_key"],
    )
    user_key.save(force_insert=True)
    MembershipEncryptionKey(
        membership=membership,
        org_encryption_key=org_key,
        sealed_org_private_key=keys["sealed_org_private_key"],
    ).save(force_insert=True)
    return org_key, user_key


class SignupView(generic.FormView):
    """
    Create a user, their organization, and all encryption keys in one transaction.

    The client derives every key from the signup password before submitting.
    The server receives only ciphertext and public keys, so the operator
    cannot decrypt stored org messages.
    """

    form_class = SignupForm
    template_name = "signup.html"

    def get_context_data(self, **kwargs):
        return super().get_context_data(**kwargs) | {"key_fields": KEY_FIELDS}

    def form_valid(self, form):
        # JavaScript-off submits carry empty hidden fields, so an absent or
        # blank key payload both mean the browser could not generate keys.
        if not all(self.request.POST.get(name) for name in KEY_FIELDS):
            form.add_error(
                None,
                _("Key generation failed. Please make sure JavaScript is enabled."),
            )
            return self.form_invalid(form)
        try:
            keys = {name: self.request.POST[name] for name in KEY_FIELDS}
            validate_encryption_keys(keys)
        except ValueError as err:
            form.add_error(None, str(err))
            return self.form_invalid(form)
        try:
            with transaction.atomic():
                user = form.save()
                org = Organization.objects.create(slug=user.username)
                membership = Membership.objects.create(
                    org=org,
                    user=user,
                    role=Membership.Role.ADMIN,
                )
                create_encryption_keys(
                    org=org, user=user, membership=membership, keys=keys
                )
                verification = EmailVerification(user=user, email=user.email)
                verification.save(force_insert=True)
                transaction.on_commit(
                    lambda: send_verification_email.enqueue(
                        email_verification_id=verification.pk
                    )
                )
        except IntegrityError:
            # A concurrent signup claimed the username (and its org slug) first.
            form.add_error(None, _("This username is already taken."))
            return self.form_invalid(form)
        login(
            self.request,
            user,
            backend="django.contrib.auth.backends.ModelBackend",
        )
        messages.info(
            self.request,
            _("We sent a verification link to %(email)s.") % {"email": user.email},
        )
        return redirect(org)


class VerifiedPasswordResetForm(PasswordResetForm):
    """
    Only send reset links to verified email addresses.

    An unverified address may belong to someone else, so mailing a reset
    link there would let anyone send relay-branded security mail to
    arbitrary addresses.
    """

    def get_users(self, email):
        return (
            user
            for user in super().get_users(email)
            if EmailVerification.objects.filter(
                user=user,
                verified_at__isnull=False,
            ).exists()
        )


class VerifiedPasswordResetView(PasswordResetView):
    """Send reset links only to verified email addresses."""

    form_class = VerifiedPasswordResetForm


class EmailVerificationView(generic.TemplateView):
    """Confirm an email address when the user opens their verification link."""

    template_name = "registration/email_verification.html"

    def get(self, request, token):
        verification = EmailVerification.fetch_by_token(token)
        if verification is None:
            state = "invalid"
        elif verification.verified_at:
            state = "already_verified"
        else:
            verification.mark_verified()
            state = "verified"
        return self.render_to_response(
            self.get_context_data(
                state=state,
                username=verification.user.username if verification else None,
            )
        )


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


class OrganizationHomeView(OrganizationScopedView, generic.View):
    """Redirect to the only live product area until VoIP ships."""

    parent = ""

    @classmethod
    def get_title(cls, request=None) -> str:
        """Return the organization name from the request's current org."""
        if request and hasattr(request, "current_org"):
            return str(request.current_org)
        return ""

    def get(self, request, *args, **kwargs):
        return redirect("email-dashboard:dashboard", org_slug=self.org.slug)


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
