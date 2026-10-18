"""Django form widgets that render as basecoat components."""

import json

from django import forms


class BasecoatSelect(forms.Select):
    """A basecoat custom select widget instead of a native select element."""

    template_name = "basecoat/select.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        values = self.format_value(value)
        context["widget"]["value_json"] = (
            json.dumps(values)
            if self.allow_multiple_selected
            else json.dumps(values[0] if values else "")
        )
        return context

    def value_from_datadict(self, data, files, name):
        if self.allow_multiple_selected:
            raw = data.get(name)
            if raw is not None:
                try:
                    parsed = json.loads(raw)
                except TypeError, ValueError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item) for item in parsed]
            try:
                getter = data.getlist
            except AttributeError:
                getter = data.get
            return getter(name)
        return super().value_from_datadict(data, files, name)


class BasecoatSelectMultiple(BasecoatSelect):
    """Multiple-select variant of :class:`BasecoatSelect`."""

    allow_multiple_selected = True
