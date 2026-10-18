from django import forms


class DebugForm(forms.Form):
    """Form exposing every common input kind and its validation errors."""

    text = forms.CharField()
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)
    url = forms.URLField()
    number = forms.IntegerField()
    float_number = forms.FloatField()
    decimal_number = forms.DecimalField()
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"})
    )
    time = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))
    boolean = forms.BooleanField(required=False)
    single_choice = forms.ChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")]
    )
    radio_choice = forms.ChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        widget=forms.RadioSelect,
    )
    multiple_choice = forms.MultipleChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        widget=forms.CheckboxSelectMultiple,
    )
    multiple_select = forms.MultipleChoiceField(
        choices=[("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")],
        widget=forms.SelectMultiple,
    )
    textarea = forms.CharField(widget=forms.Textarea)
    file = forms.FileField(required=False)
    image = forms.ImageField(required=False)
    hidden = forms.CharField(widget=forms.HiddenInput)
    color = forms.CharField(widget=forms.TextInput(attrs={"type": "color"}))
    search = forms.CharField(widget=forms.TextInput(attrs={"type": "search"}))
    tel = forms.CharField(widget=forms.TextInput(attrs={"type": "tel"}))
    slug = forms.SlugField()
    ip_address = forms.GenericIPAddressField()

    def clean(self):
        cleaned_data = super().clean()
        self.add_error(None, "Form-level error.")
        return cleaned_data
