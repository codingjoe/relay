from django import forms
from django.utils.translation import gettext_lazy as _

from abstract.network import UnsafeNetworkOperation, validate_global_url

from .models import Webhook


class WebhookForm(forms.ModelForm):
    pattern_prefix = forms.CharField(
        label=_("address pattern"),
        initial="*",
        required=False,
    )

    class Meta:
        model = Webhook
        fields = ["url", "name", "domain"]

    def __init__(self, *args, org, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["domain"].queryset = org.domains.all()

    def clean_url(self):
        url = self.cleaned_data["url"]
        try:
            validate_global_url(url)
        except UnsafeNetworkOperation as error:
            raise forms.ValidationError(
                _("Webhook URL must resolve only to public addresses.")
            ) from error
        return url

    def save(self, commit=True):
        pattern_prefix = self.cleaned_data["pattern_prefix"] or "*"
        self.instance.address_pattern = f"{pattern_prefix}@{self.instance.domain.name}"
        return super().save(commit=commit)
