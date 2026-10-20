from contextvars import ContextVar
from pathlib import Path

import django
from django.forms.renderers import DjangoTemplates, TemplatesSetting
from django.utils.functional import cached_property

admin_rendering = ContextVar("admin_rendering", default=False)


class AdminWidgetRenderer(DjangoTemplates):
    """Render form widgets with Django's stock templates, not the app's."""

    @cached_property
    def engine(self):
        django_path = Path(django.__file__).parent
        return self.backend(
            {
                "APP_DIRS": False,
                "DIRS": [
                    django_path / "forms" / "templates",
                    django_path / "contrib" / "admin" / "templates",
                ],
                "NAME": "adminforms",
                "OPTIONS": {},
            }
        )


class RelayFormRenderer(TemplatesSetting):
    """Use stock widgets in the admin and app widgets everywhere else."""

    admin_renderer = AdminWidgetRenderer()

    def get_template(self, template_name):
        if admin_rendering.get():
            return self.admin_renderer.get_template(template_name)
        return super().get_template(template_name)
