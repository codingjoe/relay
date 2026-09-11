from django.apps import AppConfig


class AbstractConfig(AppConfig):
    name = "abstract"

    def ready(self):
        from . import checks, signals  # noqa: F401
