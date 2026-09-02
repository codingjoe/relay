from django.apps import AppConfig


class DmarcConfig(AppConfig):
    name = "services.email.dmarc"

    def ready(self):
        from . import signals  # noqa: F401
