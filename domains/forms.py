from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .models import Domain, canonicalize_domain_name


class DomainCreateForm(forms.ModelForm):
    """
    Validate a domain name submitted through the dashboard.

    The platform domain itself is reserved for relay's own row, which the
    operator adds in the admin. `Domain.clean()` rejects every name below it.
    """

    class Meta:
        model = Domain
        fields = ["name"]

    def clean_name(self):
        name = canonicalize_domain_name(self.cleaned_data["name"])
        platform_name = canonicalize_domain_name(settings.RELAY_PLATFORM_DOMAIN)
        if name == platform_name or name.endswith(f".{platform_name}"):
            raise forms.ValidationError(
                _("Cannot add %(base)s or a name below it. relay manages that zone.")
                % {"base": platform_name}
            )
        return name
