from django.apps import AppConfig


class DomainsConfig(AppConfig):
    name = "domains"

    def ready(self):
        from . import signals  # noqa: F401
