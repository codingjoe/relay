from django.apps import AppConfig


class MtaConfig(AppConfig):
    name = "services.email.mta"

    def ready(self):
        from . import signals  # noqa: F401
