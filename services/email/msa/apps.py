from django.apps import AppConfig


class MsaConfig(AppConfig):
    name = "services.email.msa"

    def ready(self):
        from . import signals  # noqa: F401
