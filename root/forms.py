from django import forms
from django.utils.translation import gettext_lazy as _


class DebugForm(forms.Form):
    """Form exposing every common input kind and its validation errors."""

    text = forms.CharField(help_text=_("Short plain text."))
    email = forms.EmailField(help_text=_("An email address."))
    password = forms.CharField(
        widget=forms.PasswordInput, help_text=_("A secret password.")
    )
    url = forms.URLField(help_text=_("A full URL."))
    number = forms.IntegerField(help_text=_("An integer."))
    float_number = forms.FloatField(help_text=_("A floating point number."))
    decimal_number = forms.DecimalField(help_text=_("A decimal number."))
    date = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}), help_text=_("A calendar date.")
    )
    datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
        help_text=_("A date and time."),
    )
    time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}), help_text=_("A time of day.")
    )
    boolean = forms.BooleanField(required=False, help_text=_("A boolean flag."))
    single_choice = forms.ChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        help_text=_("Choose one option."),
    )
    radio_choice = forms.ChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        widget=forms.RadioSelect,
        help_text=_("Choose one option by radio."),
    )
    multiple_choice = forms.MultipleChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        widget=forms.CheckboxSelectMultiple,
        help_text=_("Choose several options."),
    )
    multiple_select = forms.MultipleChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        help_text=_("Choose several options from a list."),
    )
    textarea = forms.CharField(widget=forms.Textarea, help_text=_("Multiline text."))
    file = forms.FileField(required=False, help_text=_("A file upload."))
    image = forms.ImageField(required=False, help_text=_("An image upload."))
    hidden = forms.CharField(widget=forms.HiddenInput, help_text=_("A hidden value."))
    color = forms.CharField(
        widget=forms.TextInput(attrs={"type": "color"}), help_text=_("A color picker.")
    )
    search = forms.CharField(
        widget=forms.TextInput(attrs={"type": "search"}), help_text=_("A search term.")
    )
    tel = forms.CharField(
        widget=forms.TextInput(attrs={"type": "tel"}),
        help_text=_("A telephone number."),
    )
    slug = forms.SlugField(help_text=_("A slug."))
    ip_address = forms.GenericIPAddressField(help_text=_("An IP address."))

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs["aria-invalid"] = "true"

    def clean(self):
        cleaned_data = super().clean()
        self.add_error(None, _("Form-level error."))
        return cleaned_data
