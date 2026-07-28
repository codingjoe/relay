from django.apps import AppConfig


class AbstractConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "abstract"

    def ready(self):
        from . import checks  # noqa: F401
