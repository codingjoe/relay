from django import forms
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .models import Domain, canonicalize_domain_name


class DomainMtaStsForm(forms.ModelForm):
    """Validate the explicit MTA-STS MX hosts of a domain."""

    mta_sts_mx_hostnames = forms.CharField(
        label=_("MTA-STS MX hosts"),
        help_text=_(
            "One hostname or wildcard pattern per line. "
            "Empty follows the MX record hostnames."
        ),
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    class Meta:
        model = Domain
        fields = ["mta_sts_mx_hostnames"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["mta_sts_mx_hostnames"] = "\n".join(
            self.instance.mta_sts_mx_hostnames
        )
        self.fields["mta_sts_mx_hostnames"].widget.attrs["placeholder"] = "\n".join(
            settings.DNS_MX_HOSTNAMES
        )

    @staticmethod
    def parse_mta_sts_mx_hosts(value):
        """Yield canonical MTA-STS MX hosts from one hostname per line."""
        for line in value.splitlines():
            match line.strip().rstrip("."):
                case "":
                    continue
                case hostname if hostname.startswith("*."):
                    yield f"*.{canonicalize_domain_name(hostname.removeprefix('*.'))}"
                case hostname:
                    yield canonicalize_domain_name(hostname)

    def clean_mta_sts_mx_hostnames(self):
        return list(
            dict.fromkeys(
                self.parse_mta_sts_mx_hosts(self.cleaned_data["mta_sts_mx_hostnames"])
            )
        )


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
        platform_name = canonicalize_domain_name(settings.PLATFORM_DOMAIN)
        if name == platform_name or name.endswith(f".{platform_name}"):
            raise forms.ValidationError(
                _("Cannot add %(base)s or a name below it. relay manages that zone.")
                % {"base": platform_name}
            )
        return name
