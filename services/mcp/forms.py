import typing

from allauth.idp.oidc.adapter import get_adapter
from allauth.idp.oidc.forms import AuthorizationForm
from django import forms
from django.utils.translation import gettext_lazy as _


class ConsentAuthorizationForm(AuthorizationForm):
    """Ask for consent to one scope at a time."""

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        user = kwargs.pop("user")
        requested_scopes = kwargs.pop("requested_scopes")
        super().__init__(*args, user=user, requested_scopes=requested_scopes, **kwargs)
        adapter = get_adapter()
        display = adapter.scope_display

        # Drop allauth's single MultipleChoiceField so every scope becomes its
        # own checkbox with the scope name as its label and its description as
        # help text, which the form template renders like any other field.
        self.fields.pop("scopes", None)
        self.requested_scopes = list(requested_scopes)
        self.scope_fields: dict[str, str] = {}
        for scope in requested_scopes:
            field_name = f"scope_{scope.replace(':', '_').replace('-', '_')}"
            self.scope_fields[field_name] = scope
            self.fields[field_name] = forms.BooleanField(
                label=scope,
                help_text=display.get(scope, scope),
                required=False,
                initial=True,
                widget=forms.CheckboxInput,
            )

    def clean(self) -> dict[str, typing.Any]:
        cleaned_data = super().clean() or {}
        selected = [
            scope
            for field_name, scope in self.scope_fields.items()
            if cleaned_data.get(field_name)
        ]
        if not selected:
            raise forms.ValidationError(_("Select at least one permission."))
        cleaned_data["scopes"] = selected
        return cleaned_data
