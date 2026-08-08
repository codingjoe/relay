from django.apps import AppConfig


class MxConfig(AppConfig):
    name = "services.email.mx"

    def ready(self):
        from . import signals  # noqa: F401
